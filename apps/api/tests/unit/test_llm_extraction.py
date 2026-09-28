"""LLM tier: quote alignment, prompt rendering, findings → hits, merge tiers, batch runner."""

import json
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from typing import Any

import pytest

from drillsage.core.errors import BudgetExceededError, LocalOnlyViolationError
from drillsage.domain.hazards import HazardType as H
from drillsage.extract.align import align_quote
from drillsage.extract.episodes import ActivityRecord, Outcome, extract_events
from drillsage.extract.llm_extractor import (
    PROMPT_VERSION,
    SYSTEM_PROMPT,
    LLMFindings,
    ReportContext,
    findings_from,
    report_contexts,
    user_message,
)
from drillsage.extract.llm_run import pilot_sample
from drillsage.extract.schemas import ReportExtraction
from drillsage.llm.batch import BatchItem, BatchRunner, batch_params
from drillsage.llm.store import MemoryLLMStore

T0 = datetime(2020, 3, 1, tzinfo=UTC)


def act(i: int, text: str | None, *, code: str = "drilling -- drill", md: float | None = 2500,
        report_id: int = 11, wellbore: str = "W-1") -> ActivityRecord:  # fmt: skip
    return ActivityRecord(
        id=100 + i + report_id * 1000,
        wellbore=wellbore,
        report_id=report_id,
        seq=i,
        start_at=T0 + timedelta(hours=2 * i),
        end_at=T0 + timedelta(hours=2 * i + 2),
        md_m=md,
        report_md_m=2600,
        proprietary_code=code,
        state="ok",
        state_detail="success",
        comments=text,
    )


LINES = (
    act(0, 'Drilled 8 1/2" hole from 2450 m to 2510 m.'),
    act(1, "Observed seepage losses of  3 m3/hr at 2510 m. Pumped 8 m3 LCM pill,  losses stopped."),
    act(2, None),
)
CTX = ReportContext(11, "W-1", date(2020, 3, 1), 7, 0.2159, 2600, LINES)


def test_align_exact_then_normalised_else_rejected() -> None:
    text = LINES[1].comments
    assert text is not None
    exact = align_quote(text, "seepage losses")
    assert exact is not None
    assert exact.of(text) == "seepage losses"
    loose = align_quote(text, "SEEPAGE LOSSES OF 3 M3/HR")  # model collapsed the double space
    assert loose is not None
    assert loose.of(text) == "seepage losses of  3 m3/hr"
    assert align_quote(text, "severe total losses") is None
    assert align_quote(None, "x") is None
    assert align_quote(text, "   ") is None


def test_user_message_is_deterministic_and_numbered() -> None:
    message = user_message(CTX)
    assert message == user_message(CTX)
    assert "Wellbore: W-1" in message
    assert "Hole size: 8.5 in" in message
    assert "[2] 02:00-04:00 | 2500 m | drilling -- drill | ok/success" in message
    assert "[3]" in message
    assert "(no text)" in message
    assert PROMPT_VERSION.startswith("extract-v1-")
    assert "must be copied exactly" in SYSTEM_PROMPT


def _extraction(**event: Any) -> ReportExtraction:
    base = {
        "hazard": "LOST_CIRCULATION",
        "subtype": "seepage",
        "evidence": [{"line": 2, "text": "seepage losses of  3 m3/hr at 2510 m"}],
        "md_top_m": 2510,
        "md_bottom_m": None,
        "mitigations": [
            {
                "action": "Pumped LCM pill",
                "outcome": "success",
                "quote": {"line": 2, "text": "Pumped 8 m3 LCM pill"},
            }
        ],
    }
    return ReportExtraction.model_validate({"events": [{**base, **event}]})


def test_findings_become_hits_with_resolving_spans() -> None:
    findings = LLMFindings()
    findings_from(_extraction(), CTX, findings)
    activity = LINES[1]
    assert findings.events == 1
    assert findings.rejected_quotes == 0
    (hit,) = findings.hits[activity.id]
    assert hit.hazard is H.LOST_CIRCULATION
    assert hit.depths_m == (2510.0,)
    assert hit.span is not None
    assert activity.comments is not None
    assert hit.span.of(activity.comments) == "seepage losses of  3 m3/hr at 2510 m"
    (mitigation,) = findings.mitigations[(activity.id, H.LOST_CIRCULATION)]
    assert mitigation.outcome is Outcome.SUCCESS


def test_paraphrased_or_misplaced_quotes_are_dropped() -> None:
    findings = LLMFindings()
    bad = [{"line": 2, "text": "lost a lot of mud"}, {"line": 9, "text": "Drilled"}]
    findings_from(_extraction(evidence=bad, mitigations=[]), CTX, findings)
    assert (findings.events, findings.dropped_events, findings.rejected_quotes) == (0, 1, 2)
    assert dict(findings.hits) == {}


def test_merge_sets_tiers_and_combines_mitigations() -> None:
    llm_only = act(20, "Hole started to take mud slowly while drilling at 2600 m.", report_id=12)
    records = [*LINES, llm_only]
    findings = LLMFindings()
    findings_from(_extraction(), CTX, findings)
    ctx12 = ReportContext(12, "W-1", date(2020, 3, 2), 8, None, 2700, (llm_only,))
    findings_from(
        _extraction(
            evidence=[{"line": 1, "text": "take mud slowly while drilling at 2600 m"}],
            md_top_m=2600,
            mitigations=[],
        ),
        ctx12,
        findings,
    )
    events = extract_events(
        records, {"W-1": 3000}, extra_hits=findings.hits, extra_mitigations=findings.mitigations
    )
    lc = [e for e in events if e.hazard is H.LOST_CIRCULATION]
    assert [(e.confidence_tier, e.detected_by) for e in lc] == [
        ("rule+llm", "text+llm"),
        ("llm", "llm"),
    ]
    assert lc[1].md_top_m == 2600
    actions = [m.action for m in lc[0].mitigations]
    assert actions.count("Pumped LCM pill") == 1  # lexicon and LLM agree: listed once


def test_report_contexts_and_pilot_are_deterministic() -> None:
    meta = {11: (date(2020, 3, 1), 7, 0.2159, 2600.0), 12: (date(2020, 3, 2), 8, None, None)}
    other = act(0, "Ran casing to 2400 m.", report_id=12)
    contexts = report_contexts([*reversed(LINES), other], meta)
    assert [c.report_id for c in contexts] == [11, 12]
    assert [a.seq for a in contexts[0].activities] == [0, 1, 2]
    pilot = pilot_sample(contexts, 2)
    assert {c.report_id for c in pilot} == {11, 12}  # one flagged, one quiet
    assert pilot == pilot_sample(contexts, 2)
    assert len(pilot_sample(contexts, 1)) == 1


# ------------------------------------------------------------------ batch runner


@dataclass
class _Counts:
    processing: int = 0
    succeeded: int = 0


@dataclass
class _Batch:
    id: str
    processing_status: str
    request_counts: _Counts = field(default_factory=_Counts)


@dataclass
class _Text:
    text: str
    type: str = "text"


@dataclass
class _Usage:
    input_tokens: int = 1000
    output_tokens: int = 400
    cache_creation_input_tokens: int = 0
    cache_read_input_tokens: int = 1300


@dataclass
class _Msg:
    content: list[_Text]
    stop_reason: str = "end_turn"
    model: str = "claude-opus-5"
    usage: _Usage = field(default_factory=_Usage)


@dataclass
class _Result:
    type: str
    message: _Msg | None = None


@dataclass
class _Entry:
    custom_id: str
    result: _Result


class _Batches:
    def __init__(self, entries: list[_Entry]) -> None:
        self.entries = entries
        self.created: list[Any] = []
        self.polls = 0

    async def create(self, *, requests: list[Any]) -> _Batch:
        self.created = requests
        return _Batch("msgbatch_1", "in_progress")

    async def retrieve(self, batch_id: str) -> _Batch:
        self.polls += 1
        return _Batch(batch_id, "ended" if self.polls > 1 else "in_progress")

    async def results(self, batch_id: str) -> AsyncIterator[_Entry]:
        async def gen() -> AsyncIterator[_Entry]:
            for entry in reversed(self.entries):  # any order: keyed by custom_id
                yield entry

        return gen()


@dataclass
class _Client:
    batches: _Batches

    @property
    def messages(self) -> "_Client":
        return self


async def _no_sleep(_: float) -> None:
    return None


def _runner(
    entries: list[_Entry], store: MemoryLLMStore, **kw: Any
) -> tuple[BatchRunner, _Batches]:
    batches = _Batches(entries)
    runner = BatchRunner(
        _Client(batches),  # type: ignore[arg-type]
        store,
        budget_usd=kw.get("budget", 10.0),
        local_only=kw.get("local", False),
        sleep=_no_sleep,
    )
    return runner, batches


GOOD = '{"events": []}'


async def _run(runner: BatchRunner, items: list[BatchItem], estimate: float = 1.0) -> list[Any]:
    return await runner.run(
        purpose="extract",
        model="claude-opus-5",
        prompt_version="p1",
        items=items,
        schema=ReportExtraction,
        effort="medium",
        max_tokens=4000,
        estimated_cost_usd=estimate,
    )


async def test_batch_results_are_keyed_by_custom_id_and_ledgered_at_half_price() -> None:
    store = MemoryLLMStore()
    entries = [
        _Entry("r1", _Result("succeeded", _Msg([_Text(GOOD)]))),
        _Entry("r2", _Result("succeeded", _Msg([_Text("{not json")]))),
        _Entry("r3", _Result("succeeded", _Msg([_Text(GOOD)], stop_reason="refusal"))),
        _Entry("r4", _Result("expired")),
    ]
    runner, batches = _runner(entries, store)
    items = [BatchItem(f"r{i}", "sys", f"user {i}") for i in range(1, 5)]
    outcomes = await _run(runner, items)
    assert {o.custom_id: o.status for o in outcomes} == {
        "r1": "ok",
        "r2": "invalid",
        "r3": "refused",
        "r4": "expired",
    }
    assert [r["custom_id"] for r in batches.created] == ["r1", "r2", "r3", "r4"]
    assert all(c.batch for c in store.calls)
    assert store.calls[0].cost_usd == pytest.approx((1000 * 5e-6 + 1300 * 5e-7 + 400 * 25e-6) / 2)
    assert len(store.results) == 1

    rerun, _ = _runner([], store)
    again = await _run(rerun, items[:1])
    assert [o.status for o in again] == ["cached"]


async def test_batch_guards() -> None:
    items = [BatchItem("r1", "s", "u")]
    runner, _ = _runner([], MemoryLLMStore(), local=True)
    with pytest.raises(LocalOnlyViolationError):
        await _run(runner, items)
    runner, batches = _runner([], MemoryLLMStore(), budget=0.5)
    with pytest.raises(BudgetExceededError):
        await _run(runner, items, estimate=0.6)
    assert batches.created == []


def test_batch_params_carry_schema_effort_and_cached_system() -> None:
    params = batch_params(
        BatchItem("r1", "sys", "u"),
        model="claude-opus-5",
        schema=ReportExtraction,
        effort="medium",
        max_tokens=4000,
    )
    wire: dict[str, Any] = json.loads(json.dumps(params))  # what is actually sent
    assert wire["thinking"] == {"type": "adaptive"}
    assert wire["output_config"]["effort"] == "medium"
    assert wire["output_config"]["format"]["type"] == "json_schema"
    assert "events" in wire["output_config"]["format"]["schema"]["properties"]
    assert wire["system"][0]["cache_control"] == {"type": "ephemeral"}
