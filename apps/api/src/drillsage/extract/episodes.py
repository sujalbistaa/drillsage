"""Group per-activity hazard hits into events (episodes). Pure, no I/O.

One drilling problem spans many report lines: losses start while drilling, continue through
LCM pills and a trip, and are cured the next morning. Hits of the same hazard in the same
wellbore separated by less than `MAX_GAP_H` of other work become one event.
"""

from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Final

from drillsage.domain.hazards import HazardType, is_geological, severity
from drillsage.extract.rules import (
    Hit,
    HitSource,
    Span,
    classify_activity,
    mitigation_hits,
    outcome_hits,
)

MAX_GAP_H: Final = 6.0
SIDETRACK_WINDOW_H: Final = 72.0
MIN_PLAUSIBLE_DEPTH_M: Final = 10.0
DEPTH_CLUSTER_M: Final = 300.0
DEPTH_SLACK_M: Final = 100.0
"""A stated depth may exceed the deepest reported MD by this much (drilled after the report)."""
SIDETRACK_CODE: Final = "interruption -- sidetrack"


@dataclass(frozen=True, slots=True)
class ActivityRecord:
    """One activity with the context the extractor needs, loaded from the canonical model."""

    id: int
    wellbore: str
    report_id: int
    seq: int
    start_at: datetime
    end_at: datetime
    md_m: float | None
    report_md_m: float | None
    proprietary_code: str | None
    state: str | None
    state_detail: str | None
    comments: str | None

    @property
    def duration_h(self) -> float:
        return (self.end_at - self.start_at).total_seconds() / 3600.0

    @property
    def is_npt(self) -> bool:
        code = self.proprietary_code or ""
        return code.startswith("interruption") or self.state == "fail"


class EvidenceKind(StrEnum):
    CODE = "code"
    TRIGGER = "trigger"
    MITIGATION = "mitigation"
    OUTCOME = "outcome"


class Outcome(StrEnum):
    SUCCESS = "success"
    FAILURE = "failure"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class Evidence:
    activity_id: int
    kind: EvidenceKind
    rule_id: str
    span: Span | None


@dataclass(frozen=True, slots=True)
class Mitigation:
    action: str
    outcome: Outcome
    activity_id: int
    span: Span
    outcome_activity_id: int | None
    outcome_span: Span | None


@dataclass
class EventDraft:
    wellbore: str
    hazard: HazardType
    activities: list[ActivityRecord] = field(default_factory=list)
    hits: list[tuple[ActivityRecord, Hit]] = field(default_factory=list)

    @property
    def start_at(self) -> datetime:
        return min(a.start_at for a in self.activities)

    @property
    def end_at(self) -> datetime:
        return max(a.end_at for a in self.activities)


@dataclass(frozen=True, slots=True)
class Event:
    wellbore: str
    hazard: HazardType
    subtype: str | None
    start_at: datetime
    end_at: datetime
    md_top_m: float | None
    md_bottom_m: float | None
    depth_source: str
    """`text` (stated in the report), `activity` (activity depth) or `report` (hole depth)."""
    report_id: int
    """Report of the first activity: hole size and mud come from here."""
    npt_h: float
    severity: int
    led_to_sidetrack: bool
    detected_by: str
    """Contributing sources joined by `+`: `code`, `text`, `llm`."""
    confidence_tier: str
    activity_ids: tuple[int, ...]
    evidence: tuple[Evidence, ...]
    mitigations: tuple[Mitigation, ...]
    rule_ids: tuple[str, ...]


def group_into_episodes(
    records: Sequence[ActivityRecord],
    extra_hits: Mapping[int, Sequence[Hit]] | None = None,
) -> list[EventDraft]:
    """Hits of one hazard in one wellbore, split where more than `MAX_GAP_H` passes without one.

    `extra_hits` (activity id → hits) adds findings from other extractors, such as the LLM
    tier, so every source goes through the same episode logic.
    """
    extra = extra_hits or {}
    by_key: dict[tuple[str, HazardType], list[tuple[ActivityRecord, Hit]]] = defaultdict(list)
    for record in sorted(records, key=lambda r: (r.wellbore, r.start_at, r.id)):
        found = [
            *classify_activity(record.proprietary_code, record.state_detail, record.comments),
            *extra.get(record.id, ()),
        ]
        for hit in found:
            by_key[(record.wellbore, hit.hazard)].append((record, hit))

    drafts: list[EventDraft] = []
    gap = timedelta(hours=MAX_GAP_H)
    for (wellbore, hazard), hits in sorted(by_key.items()):
        current: EventDraft | None = None
        for record, hit in hits:
            if current is None or record.start_at - current.end_at > gap:
                current = EventDraft(wellbore, hazard)
                drafts.append(current)
            if record not in current.activities:
                current.activities.append(record)
            current.hits.append((record, hit))
    return drafts


def _depths(
    draft: EventDraft, max_md_m: float | None, mudline_md_m: float | None
) -> tuple[float | None, float | None, str]:
    """Where the problem happened, not where the bit travelled while handling it.

    Candidates come only from trigger evidence: depths stated in trigger sentences, then the
    depth of trigger activities, then the hole depth when the event began. Trips produce shallow
    numbers (`POOH from 3245 m to 13 m`), so the range is the cluster within `DEPTH_CLUSTER_M` of
    the deepest candidate, since problems are overwhelmingly met near the bit.
    """
    ceiling = (max_md_m + DEPTH_SLACK_M) if max_md_m is not None else float("inf")
    floor = MIN_PLAUSIBLE_DEPTH_M
    if is_geological(draft.hazard) and mudline_md_m is not None:
        floor = max(floor, mudline_md_m)  # a formation problem cannot be above the seabed

    def plausible(values: Iterable[float | None]) -> list[float]:
        return [v for v in values if v is not None and floor <= v <= ceiling]

    triggers = [(record, hit) for record, hit in draft.hits if hit.source is not HitSource.CODE]
    onset = min(draft.activities, key=lambda a: (a.start_at, a.id))
    for source, values in (
        ("text", plausible(d for _, hit in triggers for d in hit.depths_m)),
        ("activity", plausible(record.md_m for record, _ in draft.hits)),
        ("report", plausible([onset.report_md_m])),
    ):
        if values:
            deepest = max(values)
            return min(v for v in values if v >= deepest - DEPTH_CLUSTER_M), deepest, source
    return None, None, "none"


def _mitigations(
    draft: EventDraft, extra: Mapping[tuple[int, HazardType], Sequence[Mitigation]]
) -> list[Mitigation]:
    ordered = sorted(draft.activities, key=lambda a: (a.start_at, a.id))
    found: dict[str, Mitigation] = {}
    for index, activity in enumerate(ordered):
        for mitigation in mitigation_hits(activity.comments):
            if draft.hazard not in mitigation.hazards or mitigation.action in found:
                continue
            outcome, outcome_activity, outcome_span = Outcome.UNKNOWN, None, None
            candidates = [(activity, mitigation.span.end)] + [(a, 0) for a in ordered[index + 1 :]]
            for later, after in candidates:
                hit = next((o for o in outcome_hits(later.comments) if o.span.start >= after), None)
                if hit is not None:
                    outcome = Outcome.SUCCESS if hit.success else Outcome.FAILURE
                    outcome_activity, outcome_span = later.id, hit.span
                    break
            found[mitigation.action] = Mitigation(
                action=mitigation.action,
                outcome=outcome,
                activity_id=activity.id,
                span=mitigation.span,
                outcome_activity_id=outcome_activity,
                outcome_span=outcome_span,
            )
    known = {action.casefold() for action in found}
    for activity in ordered:
        for llm_mitigation in extra.get((activity.id, draft.hazard), ()):
            if llm_mitigation.action.casefold() not in known:
                known.add(llm_mitigation.action.casefold())
                found[llm_mitigation.action] = llm_mitigation
    return list(found.values())


def _led_to_sidetrack(draft: EventDraft, wellbore_records: Sequence[ActivityRecord]) -> bool:
    window_end = draft.end_at + timedelta(hours=SIDETRACK_WINDOW_H)
    return any(
        r.proprietary_code == SIDETRACK_CODE and draft.start_at <= r.start_at <= window_end
        for r in wellbore_records
    )


def confidence_tier(sources: set[HitSource]) -> str:
    """`rule` (codes and lexicon), `llm`, or `rule+llm` when both found the problem."""
    rule = bool(sources & {HitSource.CODE, HitSource.TEXT})
    llm = HitSource.LLM in sources
    if rule and llm:
        return "rule+llm"
    return "llm" if llm else "rule"


def finalise(
    draft: EventDraft,
    wellbore_records: Sequence[ActivityRecord],
    max_md_m: float | None,
    mudline_md_m: float | None = None,
    extra_mitigations: Mapping[tuple[int, HazardType], Sequence[Mitigation]] | None = None,
) -> Event:
    md_top, md_bottom, depth_source = _depths(draft, max_md_m, mudline_md_m)
    npt_h = sum(a.duration_h for a in draft.activities if a.is_npt)
    sidetrack = _led_to_sidetrack(draft, wellbore_records)
    sources = {hit.source for _, hit in draft.hits}
    detected_by = "+".join(s.value for s in HitSource if s in sources)
    subtypes = [hit.subtype for _, hit in draft.hits if hit.subtype]
    mitigations = _mitigations(draft, extra_mitigations or {})

    evidence: list[Evidence] = [
        Evidence(
            record.id,
            EvidenceKind.CODE if hit.source is HitSource.CODE else EvidenceKind.TRIGGER,
            hit.rule_id,
            hit.span,
        )
        for record, hit in draft.hits
    ]
    for m in mitigations:
        evidence.append(Evidence(m.activity_id, EvidenceKind.MITIGATION, m.action, m.span))
        if m.outcome_activity_id is not None:
            evidence.append(
                Evidence(
                    m.outcome_activity_id, EvidenceKind.OUTCOME, m.outcome.value, m.outcome_span
                )
            )
    first = min(draft.activities, key=lambda a: (a.start_at, a.id))
    return Event(
        wellbore=draft.wellbore,
        hazard=draft.hazard,
        subtype=max(set(subtypes), key=subtypes.count) if subtypes else None,
        start_at=draft.start_at,
        end_at=draft.end_at,
        md_top_m=md_top,
        md_bottom_m=md_bottom,
        depth_source=depth_source,
        report_id=first.report_id,
        npt_h=round(npt_h, 3),
        severity=severity(npt_h, led_to_sidetrack=sidetrack),
        led_to_sidetrack=sidetrack,
        detected_by=detected_by,
        confidence_tier=confidence_tier(sources),
        activity_ids=tuple(sorted({a.id for a in draft.activities})),
        evidence=tuple(evidence),
        mitigations=tuple(mitigations),
        rule_ids=tuple(sorted({hit.rule_id for _, hit in draft.hits})),
    )


def extract_events(
    records: Sequence[ActivityRecord],
    max_md_by_wellbore: dict[str, float],
    mudline_md_by_wellbore: dict[str, float] | None = None,
    *,
    extra_hits: Mapping[int, Sequence[Hit]] | None = None,
    extra_mitigations: Mapping[tuple[int, HazardType], Sequence[Mitigation]] | None = None,
) -> list[Event]:
    """All rule-tier events for the given activities, deterministic in order.

    `mudline_md_by_wellbore` (kelly-bushing elevation + water depth) is the shallowest
    plausible depth for a geological hazard.
    """
    mudlines = mudline_md_by_wellbore or {}
    by_wellbore: dict[str, list[ActivityRecord]] = defaultdict(list)
    for record in records:
        by_wellbore[record.wellbore].append(record)
    events = [
        finalise(
            draft,
            by_wellbore[draft.wellbore],
            max_md_by_wellbore.get(draft.wellbore),
            mudlines.get(draft.wellbore),
            extra_mitigations,
        )
        for draft in group_into_episodes(records, extra_hits)
    ]
    return sorted(events, key=lambda e: (e.wellbore, e.start_at, e.hazard.value))
