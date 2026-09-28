"""LLM tier: one structured-output call per daily report, turned into hits with exact spans.

The model sees the report's numbered activity lines and returns events with verbatim quotes.
Quotes are aligned to the stored comments here; an event with no quote found in the source
is dropped and counted, so every LLM evidence span resolves to real report text.
"""

import hashlib
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date
from importlib import resources
from typing import Final

from drillsage.domain.hazards import HazardType
from drillsage.extract.align import align_quote
from drillsage.extract.episodes import ActivityRecord, Mitigation, Outcome
from drillsage.extract.rules import Hit, HitSource
from drillsage.extract.schemas import ReportExtraction

PURPOSE: Final = "extract"
SYSTEM_PROMPT: Final = (
    resources.files("drillsage.extract.prompts").joinpath("extract_v1.md").read_text("utf-8")
)
PROMPT_VERSION: Final = (
    f"extract-v1-{hashlib.sha256(SYSTEM_PROMPT.encode('utf-8')).hexdigest()[:8]}"
)
"""Changes whenever the prompt text changes, which invalidates cached results."""

_M_PER_IN: Final = 0.0254


@dataclass(frozen=True, slots=True)
class ReportContext:
    report_id: int
    wellbore: str
    day: date
    report_no: int | None
    hole_diameter_m: float | None
    md_m: float | None
    activities: tuple[ActivityRecord, ...]
    """In report order; line n in the prompt is `activities[n - 1]`."""


@dataclass
class LLMFindings:
    hits: dict[int, list[Hit]] = field(default_factory=lambda: defaultdict(list))
    mitigations: dict[tuple[int, HazardType], list[Mitigation]] = field(
        default_factory=lambda: defaultdict(list)
    )
    events: int = 0
    dropped_events: int = 0
    rejected_quotes: int = 0


def user_message(ctx: ReportContext) -> str:
    """Deterministic rendering of one report (no timestamps of the run, stable ordering)."""
    hole = f"{ctx.hole_diameter_m / _M_PER_IN:g} in" if ctx.hole_diameter_m else "not reported"
    depth = f"{ctx.md_m:g} m MD" if ctx.md_m is not None else "not reported"
    report_no = ctx.report_no if ctx.report_no is not None else "?"
    lines = [
        f"Wellbore: {ctx.wellbore}",
        f"Report: {ctx.day.isoformat()} (report {report_no})",
        f"Hole size: {hole} | Hole depth at report end: {depth}",
        "",
        "Activities:",
    ]
    for n, a in enumerate(ctx.activities, start=1):
        md = f"{a.md_m:g} m" if a.md_m else "depth n/a"
        status = "/".join(x for x in (a.state, a.state_detail) if x) or "n/a"
        lines.append(
            f"[{n}] {a.start_at:%H:%M}-{a.end_at:%H:%M} | {md} | "
            f"{a.proprietary_code or 'no code'} | {status}"
        )
        lines.append((a.comments or "").strip() or "(no text)")
    return "\n".join(lines)


def _activity(ctx: ReportContext, line: int) -> ActivityRecord | None:
    return ctx.activities[line - 1] if 1 <= line <= len(ctx.activities) else None


def findings_from(extraction: ReportExtraction, ctx: ReportContext, into: LLMFindings) -> None:
    """Convert one validated extraction into hits and mitigations (mutates `into`)."""
    rule_id = f"llm.{PROMPT_VERSION}"
    for event in extraction.events:
        depths = tuple(d for d in (event.md_top_m, event.md_bottom_m) if d is not None)
        aligned: list[tuple[ActivityRecord, Hit]] = []
        for quote in event.evidence:
            activity = _activity(ctx, quote.line)
            span = align_quote(activity.comments if activity else None, quote.text)
            if activity is None or span is None:
                into.rejected_quotes += 1
                continue
            aligned.append(
                (activity, Hit(event.hazard, rule_id, HitSource.LLM, span, event.subtype, depths))
            )
        if not aligned:
            into.dropped_events += 1
            continue
        into.events += 1
        for activity, hit in aligned:
            into.hits[activity.id].append(hit)
        for mitigation in event.mitigations:
            activity = _activity(ctx, mitigation.quote.line)
            span = align_quote(activity.comments if activity else None, mitigation.quote.text)
            if activity is None or span is None:
                into.rejected_quotes += 1
                continue
            into.mitigations[(activity.id, event.hazard)].append(
                Mitigation(
                    action=mitigation.action,
                    outcome=Outcome(mitigation.outcome),
                    activity_id=activity.id,
                    span=span,
                    outcome_activity_id=None,
                    outcome_span=None,
                )
            )


def report_contexts(
    records: Sequence[ActivityRecord],
    meta: Mapping[int, tuple[date, int | None, float | None, float | None]],
) -> list[ReportContext]:
    """Group activities by report. `meta`: report id → (day, report no, hole diameter, md)."""
    by_report: dict[int, list[ActivityRecord]] = defaultdict(list)
    for record in records:
        by_report[record.report_id].append(record)
    contexts = []
    for report_id, activities in sorted(by_report.items()):
        day, report_no, hole, md = meta[report_id]
        ordered = tuple(sorted(activities, key=lambda a: (a.seq, a.start_at)))
        contexts.append(
            ReportContext(report_id, ordered[0].wellbore, day, report_no, hole, md, ordered)
        )
    return contexts
