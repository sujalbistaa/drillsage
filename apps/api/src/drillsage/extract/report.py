"""Extraction report (`eval/reports/extraction_rules.{md,json}`).

This is not an accuracy report: accuracy needs the hand-verified gold set (Phase 2c). It
states what each tier found, how often text evidence corroborates the operator's own codes,
what text finds that the codes never flag, and whether every evidence span resolves to
source text.
"""

import json
from pathlib import Path
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from drillsage.db import models as m
from drillsage.domain.hazards import HazardType, is_geological
from drillsage.extract.llm_extractor import PROMPT_VERSION
from drillsage.extract.rules import RULES_VERSION


def _round(value: float | None, digits: int = 1) -> float | None:
    return None if value is None else round(value, digits)


async def collect(session: AsyncSession) -> dict[str, Any]:
    e = m.Event
    rows = (
        await session.execute(
            select(
                e.hazard,
                func.count(),
                func.count(func.distinct(e.wellbore_id)),
                func.sum(e.npt_h),
                func.count().filter(e.detected_by == "code"),
                func.count().filter(e.detected_by == "text"),
                func.count().filter(e.detected_by == "code+text"),
                func.count().filter(e.md_top_m.is_not(None)),
                func.count().filter(e.depth_source == "text"),
                func.count().filter(e.formation.is_not(None)),
                func.count().filter(func.jsonb_array_length(e.mitigations) > 0),
                func.count().filter(e.severity >= 3),  # noqa: PLR2004 - major events
                func.count().filter(e.led_to_sidetrack),
                func.count().filter(e.confidence_tier == "rule"),
                func.count().filter(e.confidence_tier == "rule+llm"),
                func.count().filter(e.confidence_tier == "llm"),
            ).group_by(e.hazard)
        )
    ).tuples()
    hazards: list[dict[str, Any]] = []
    for (
        hazard,
        n,
        wellbores,
        npt,
        code_only,
        text_only,
        both,
        with_depth,
        text_depth,
        with_formation,
        with_mitigation,
        major,
        sidetrack,
        tier_rule,
        tier_both,
        tier_llm,
    ) in rows:
        coded = code_only + both
        hazards.append(
            {
                "hazard": hazard,
                "geological": is_geological(HazardType(hazard)),
                "events": n,
                "wellbores": wellbores,
                "npt_h": _round(npt),
                "detected_by_code_only": code_only,
                "detected_by_text_only": text_only,
                "detected_by_both": both,
                "code_events_corroborated_by_text_pct": _round(100 * both / coded)
                if coded
                else None,
                "with_depth_pct": _round(100 * with_depth / n),
                "depth_stated_in_text_pct": _round(100 * text_depth / n),
                "with_formation_pct": _round(100 * with_formation / n),
                "with_mitigation_pct": _round(100 * with_mitigation / n),
                "severity_3_or_4": major,
                "led_to_sidetrack": sidetrack,
                "tier_rule": tier_rule,
                "tier_rule_llm": tier_both,
                "tier_llm": tier_llm,
            }
        )
    hazards.sort(key=lambda h: (not h["geological"], -h["events"]))

    ev = m.EventEvidence
    comments_text = func.coalesce(m.Activity.comments, "")
    spans = (
        await session.execute(
            select(
                func.count(),
                func.count().filter(ev.char_end <= func.char_length(comments_text)),
            )
            .join(m.Activity, m.Activity.id == ev.activity_id)
            .where(ev.char_start.is_not(None))
        )
    ).one()
    by_formation = (
        await session.execute(
            select(e.formation, e.hazard, func.count(), func.sum(e.npt_h))
            .where(e.formation.is_not(None))
            .where(e.hazard.in_([h.value for h in HazardType if is_geological(h)]))
            .group_by(e.formation, e.hazard)
            .order_by(func.count().desc())
            .limit(15)
        )
    ).tuples()
    llm = (
        await session.execute(
            select(func.count(), func.coalesce(func.sum(m.LLMExtraction.rejected_quotes), 0)).where(
                m.LLMExtraction.prompt_version == PROMPT_VERSION
            )
        )
    ).one()
    reports = await session.scalar(select(func.count()).select_from(m.DailyReport))
    return {
        "extractor_version": RULES_VERSION,
        "llm_prompt_version": PROMPT_VERSION,
        "llm_reports": llm[0],
        "reports": reports,
        "llm_rejected_quotes": int(llm[1]),
        "events": sum(h["events"] for h in hazards),
        "npt_h": _round(sum(h["npt_h"] or 0 for h in hazards)),
        "hazards": hazards,
        "evidence_spans": {"total": spans[0], "resolving_to_source_text": spans[1]},
        "top_formation_hazards": [
            {"formation": f, "hazard": h, "events": n, "npt_h": _round(npt)}
            for f, h, n, npt in by_formation
        ],
    }


def _cell(value: object) -> str:
    if value is None:
        return "-"
    if isinstance(value, bool):
        return "yes" if value else ""
    return f"{value:,}" if isinstance(value, int) else str(value)


def write(payload: dict[str, Any], out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "extraction_rules.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    columns = (
        ("hazard", "Hazard"),
        ("geological", "Geological"),
        ("events", "Events"),
        ("wellbores", "Wellbores"),
        ("npt_h", "NPT (h)"),
        ("detected_by_code_only", "Code only"),
        ("detected_by_both", "Code + text"),
        ("detected_by_text_only", "Text only"),
        ("code_events_corroborated_by_text_pct", "Code events with text evidence (%)"),
        ("depth_stated_in_text_pct", "Depth stated in text (%)"),
        ("with_formation_pct", "With formation (%)"),
        ("with_mitigation_pct", "With mitigation (%)"),
        ("severity_3_or_4", "Severity 3-4"),
        ("tier_rule", "Tier rule"),
        ("tier_rule_llm", "Tier rule+llm"),
        ("tier_llm", "Tier llm"),
    )
    header = "| " + " | ".join(t for _, t in columns) + " |"
    align = "|---|---|" + "---:|" * (len(columns) - 2)
    body = "\n".join(
        "| " + " | ".join(_cell(h[k]) for k, _ in columns) + " |" for h in payload["hazards"]
    )
    spans = payload["evidence_spans"]
    formations = "\n".join(
        f"| {r['formation']} | {r['hazard']} | {r['events']} | {_cell(r['npt_h'])} |"
        for r in payload["top_formation_hazards"]
    )
    md = f"""# Event extraction

Generated by `make extract` (`drillsage-data extract`). Do not edit by hand.
Rules `{payload["extractor_version"]}`; LLM prompt `{payload["llm_prompt_version"]}` has read
{payload["llm_reports"]:,} of {payload["reports"]:,} daily reports
({payload["llm_rejected_quotes"]:,} LLM quotes did not match the source text and were dropped).

**{payload["events"]:,} events, {payload["npt_h"]:,} h of non-productive time.** Every text
evidence span resolves to its source sentence: {spans["resolving_to_source_text"]:,} of
{spans["total"]:,}.

**What this report is and is not.** It is not an accuracy measurement; precision and recall
per hazard come from the hand-verified gold set. It shows what the deterministic tier finds
and how that relates to the operator's own activity codes:

- *Code only*: the operator coded the problem, but no report sentence was recognised.
- *Code + text*: both agree; the text adds the depth, the numbers and the fix.
- *Text only*: problems the codes never flag. Tight hole and wellbore instability have no
  operator code at all, so every one of those events exists only because of the text.

{header}
{align}
{body}

Geological hazards drive look-ahead depth alerts; the others are counted as NPT only.
Events group consecutive report lines about one problem (gap under 6 h). Depth is where the
problem was met: the depths stated in trigger sentences, else the activity depth, else the
hole depth, clustered near the deepest value because problems are met near the bit.

## Where geological problems happened (top formations by events)

| Formation | Hazard | Events | NPT (h) |
|---|---|---:|---:|
{formations}

## Known limits

- Operator codes label whole episodes: a fishing job's toolbox talks are coded `fish`. Codes
  seed events but are never used as text evidence.
- The lexicon is tuned on Volve's English reports; wording outside it is missed in reports the
  LLM tier has not read yet.
- Mitigation outcomes are found only when a success or failure phrase follows the action in the
  same episode; otherwise the outcome is `unknown`.
"""
    (out_dir / "extraction_rules.md").write_text(md, encoding="utf-8")
