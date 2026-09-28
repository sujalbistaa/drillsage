"""Build events from the rule tier plus any stored LLM results, and store them with evidence.

The `events` table is fully derived: every run rebuilds it from the rules (deterministic,
free) merged with the LLM results already stored for the current prompt version (free: no
model is called here). Each event's `confidence_tier` says which tiers found it.
"""

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from sqlalchemy import delete, func, insert, select
from sqlalchemy.ext.asyncio import AsyncSession

from drillsage.core.logging import get_logger
from drillsage.db import models as m
from drillsage.db.repositories import load_formation_tops, load_trajectories
from drillsage.domain.formations import FormationTop, StratLevel, unit_at_md
from drillsage.domain.trajectory import Trajectory
from drillsage.extract.episodes import ActivityRecord, Event, extract_events
from drillsage.extract.llm_extractor import PROMPT_VERSION
from drillsage.extract.llm_run import load_contexts, load_findings
from drillsage.extract.rules import RULES_VERSION

log = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class _Mud:
    at: datetime | None
    report_id: int
    density_gcc: float
    mud_class: str | None


@dataclass
class ExtractionStats:
    activities: int = 0
    events: int = 0
    evidence: int = 0
    by_hazard: dict[str, int] = field(default_factory=dict)
    by_tier: dict[str, int] = field(default_factory=dict)
    llm_reports: int = 0
    llm_events: int = 0
    llm_dropped_events: int = 0
    llm_rejected_quotes: int = 0


async def load_activity_records(
    session: AsyncSession,
) -> tuple[list[ActivityRecord], dict[str, int]]:
    """Every activity with its report context, plus wellbore name → id."""
    rows = await session.execute(
        select(
            m.Activity.id,
            m.Wellbore.name,
            m.Activity.report_id,
            m.Activity.seq,
            m.Activity.start_at,
            m.Activity.end_at,
            m.Activity.md_m,
            m.DailyReport.md_m,
            m.Activity.proprietary_code,
            m.Activity.state,
            m.Activity.state_detail,
            m.Activity.comments,
        )
        .join(m.DailyReport, m.DailyReport.id == m.Activity.report_id)
        .join(m.Wellbore, m.Wellbore.id == m.Activity.wellbore_id)
        .where(m.Activity.start_at.is_not(None), m.Activity.end_at.is_not(None))
        .order_by(m.Wellbore.name, m.Activity.start_at, m.Activity.id)
    )
    records = [
        ActivityRecord(
            id=aid,
            wellbore=wellbore,
            report_id=report_id,
            seq=seq,
            start_at=start,
            end_at=end,
            md_m=md,
            report_md_m=report_md,
            proprietary_code=code,
            state=state,
            state_detail=detail,
            comments=comments,
        )
        for (
            aid,
            wellbore,
            report_id,
            seq,
            start,
            end,
            md,
            report_md,
            code,
            state,
            detail,
            comments,
        ) in rows.tuples()
    ]
    ids = dict((await session.execute(select(m.Wellbore.name, m.Wellbore.id))).tuples().all())
    return records, ids


async def _muds(session: AsyncSession) -> dict[int, list[_Mud]]:
    rows = await session.execute(
        select(
            m.DailyReport.wellbore_id,
            m.Fluid.at,
            m.Fluid.report_id,
            m.Fluid.density_gcc,
            m.Fluid.mud_class,
        )
        .join(m.DailyReport, m.DailyReport.id == m.Fluid.report_id)
        .where(m.Fluid.density_gcc.is_not(None))
    )
    muds: dict[int, list[_Mud]] = defaultdict(list)
    for wid, at, report_id, density, mud_class in rows.tuples():
        if density is not None:
            muds[wid].append(_Mud(at, report_id, density, mud_class))
    return muds


def _mud_for(event: Event, candidates: list[_Mud]) -> _Mud | None:
    """Mud of the event's report if sampled there, else the sample closest in time."""
    same_report = [c for c in candidates if c.report_id == event.report_id]
    pool = same_report or [c for c in candidates if c.at is not None]
    if not pool:
        return None
    return min(pool, key=lambda c: abs((c.at or event.start_at) - event.start_at))


def _formation(
    tops: list[FormationTop], md: float | None
) -> tuple[str | None, str | None, str | None]:
    if md is None:
        return None, None, None
    formation = unit_at_md(tops, md, StratLevel.FORMATION)
    group = unit_at_md(tops, md, StratLevel.GROUP)
    located = formation or group
    source = located.source.value if located is not None else None
    return (
        formation.name if formation else None,
        group.name if group else None,
        source,
    )


def _event_row(
    event: Event,
    *,
    wellbore_id: int,
    trajectory: Trajectory | None,
    kb_m: float | None,
    tops: list[FormationTop],
    hole_diameter_m: float | None,
    mud: _Mud | None,
) -> dict[str, Any]:
    def tvd(md: float | None) -> float | None:
        return trajectory.tvd_at_md(md) if trajectory is not None and md is not None else None

    tvd_top, tvd_bottom = tvd(event.md_top_m), tvd(event.md_bottom_m)
    formation, group, formation_source = _formation(tops, event.md_top_m)
    return {
        "wellbore_id": wellbore_id,
        "hazard": event.hazard.value,
        "subtype": event.subtype,
        "start_at": event.start_at,
        "end_at": event.end_at,
        "md_top_m": event.md_top_m,
        "md_bottom_m": event.md_bottom_m,
        "depth_source": event.depth_source,
        "tvd_top_m": tvd_top,
        "tvd_bottom_m": tvd_bottom,
        "tvdss_top_m": tvd_top - kb_m if tvd_top is not None and kb_m is not None else None,
        "tvdss_bottom_m": (
            tvd_bottom - kb_m if tvd_bottom is not None and kb_m is not None else None
        ),
        "formation": formation,
        "formation_group": group,
        "formation_source": formation_source,
        "hole_diameter_m": hole_diameter_m,
        "mud_density_gcc": mud.density_gcc if mud else None,
        "mud_class": mud.mud_class if mud else None,
        "severity": event.severity,
        "npt_h": event.npt_h,
        "led_to_sidetrack": event.led_to_sidetrack,
        "detected_by": event.detected_by,
        "confidence_tier": event.confidence_tier,
        "extractor_version": (
            RULES_VERSION
            if event.confidence_tier == "rule"
            else f"{RULES_VERSION}+{PROMPT_VERSION}"
        ),
        "n_activities": len(event.activity_ids),
        "mitigations": [
            {
                "action": mt.action,
                "outcome": mt.outcome.value,
                "activity_id": mt.activity_id,
                "span": [mt.span.start, mt.span.end],
                "outcome_activity_id": mt.outcome_activity_id,
                "outcome_span": (
                    [mt.outcome_span.start, mt.outcome_span.end] if mt.outcome_span else None
                ),
            }
            for mt in event.mitigations
        ],
    }


async def run_extraction(session: AsyncSession) -> ExtractionStats:
    """Rebuild all events. Commits on success; nothing is written on failure."""
    records, wellbore_ids = await load_activity_records(session)
    max_md = {
        name: md
        for name, md in (
            await session.execute(
                select(m.Wellbore.name, func.max(m.DailyReport.md_m))
                .join(m.DailyReport, m.DailyReport.wellbore_id == m.Wellbore.id)
                .group_by(m.Wellbore.name)
            )
        ).tuples()
        if md is not None
    }
    mudline = {
        name: kb + water
        for name, kb, water in (
            await session.execute(
                select(m.Wellbore.name, m.Wellbore.kb_elevation_m, m.Wellbore.water_depth_m)
            )
        ).tuples()
        if kb is not None and water is not None
    }
    contexts = await load_contexts(session, records)
    findings, llm_reports = await load_findings(session, contexts)
    events = extract_events(
        records,
        max_md,
        mudline,
        extra_hits=findings.hits,
        extra_mitigations=findings.mitigations,
    )

    trajectories = await load_trajectories(session)
    tops = await load_formation_tops(session)
    muds = await _muds(session)
    kb = dict(
        (await session.execute(select(m.Wellbore.id, m.Wellbore.kb_elevation_m))).tuples().all()
    )
    holes = dict(
        (await session.execute(select(m.DailyReport.id, m.DailyReport.hole_diameter_m)))
        .tuples()
        .all()
    )

    stats = ExtractionStats(
        activities=len(records),
        llm_reports=llm_reports,
        llm_events=findings.events,
        llm_dropped_events=findings.dropped_events,
        llm_rejected_quotes=findings.rejected_quotes,
    )
    try:
        await session.execute(delete(m.Event))
        for event in events:
            wid = wellbore_ids[event.wellbore]
            row = _event_row(
                event,
                wellbore_id=wid,
                trajectory=trajectories.get(wid),
                kb_m=kb.get(wid),
                tops=tops.get(wid, []),
                hole_diameter_m=holes.get(event.report_id),
                mud=_mud_for(event, muds.get(wid, [])),
            )
            event_id: int = (
                await session.execute(insert(m.Event).values(**row).returning(m.Event.id))
            ).scalar_one()
            evidence = [
                {
                    "event_id": event_id,
                    "activity_id": ev.activity_id,
                    "kind": ev.kind.value,
                    "rule_id": ev.rule_id,
                    "char_start": ev.span.start if ev.span else None,
                    "char_end": ev.span.end if ev.span else None,
                }
                for ev in event.evidence
            ]
            await session.execute(insert(m.EventEvidence), evidence)
            stats.evidence += len(evidence)
            stats.by_hazard[event.hazard.value] = stats.by_hazard.get(event.hazard.value, 0) + 1
            stats.by_tier[event.confidence_tier] = stats.by_tier.get(event.confidence_tier, 0) + 1
    except BaseException:
        await session.rollback()
        raise
    await session.commit()
    stats.events = len(events)
    stats.by_hazard = dict(sorted(stats.by_hazard.items()))
    stats.by_tier = dict(sorted(stats.by_tier.items()))
    log.info(
        "extraction_complete", events=stats.events, evidence=stats.evidence, llm_reports=llm_reports
    )
    return stats
