"""Run the LLM tier over daily reports and read stored results back for merging.

Nothing here decides whether money may be spent: the CLI shows an estimate and requires an
explicit `--yes`, and the gateway / batch runner enforce the budget and local-only mode.
"""

import random
from collections.abc import Sequence
from datetime import date
from typing import Final

from pydantic import ValidationError
from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from drillsage.core.config import Settings
from drillsage.core.logging import get_logger
from drillsage.db import models as m
from drillsage.domain.hazards import is_geological
from drillsage.extract.episodes import ActivityRecord
from drillsage.extract.llm_extractor import (
    PROMPT_VERSION,
    PURPOSE,
    SYSTEM_PROMPT,
    LLMFindings,
    ReportContext,
    findings_from,
    report_contexts,
    user_message,
)
from drillsage.extract.rules import classify_activity
from drillsage.extract.schemas import ReportExtraction
from drillsage.llm.batch import BatchItem, BatchOutcome, BatchRunner
from drillsage.llm.estimate import CostEstimate, estimate
from drillsage.llm.gateway import LLMGateway

log = get_logger(__name__)

PILOT_SEED: Final = 20260928


async def load_contexts(
    session: AsyncSession, records: Sequence[ActivityRecord]
) -> list[ReportContext]:
    rows = await session.execute(
        select(
            m.DailyReport.id,
            m.DailyReport.start_at,
            m.DailyReport.report_no,
            m.DailyReport.hole_diameter_m,
            m.DailyReport.md_m,
        )
    )
    meta: dict[int, tuple[date, int | None, float | None, float | None]] = {
        rid: (start.date(), no, hole, md) for rid, start, no, hole, md in rows.tuples()
    }
    return report_contexts(records, meta)


def pilot_sample(contexts: Sequence[ReportContext], size: int) -> list[ReportContext]:
    """Half reports where the rule tier saw a geological hazard, half from the rest.

    Deterministic (fixed seed) so the pilot, its cost and its results are reproducible, and
    stratified so the pilot measures both agreement with the rules and what the rules miss.
    """
    flagged: list[ReportContext] = []
    other: list[ReportContext] = []
    for ctx in contexts:
        geological = any(
            is_geological(hit.hazard)
            for a in ctx.activities
            for hit in classify_activity(a.proprietary_code, a.state_detail, a.comments)
        )
        (flagged if geological else other).append(ctx)
    rng = random.Random(PILOT_SEED)  # noqa: S311 - sampling, not security
    half = size // 2
    chosen = rng.sample(flagged, min(half, len(flagged)))
    chosen += rng.sample(other, min(size - len(chosen), len(other)))
    return sorted(chosen, key=lambda c: c.report_id)


MIN_PILOT_CALLS: Final = 10


async def measured_output_tokens(session: AsyncSession) -> float | None:
    """Mean output tokens of successful extraction calls, once a pilot has made enough."""
    count, mean = (
        await session.execute(
            select(func.count(), func.avg(m.LLMCall.output_tokens)).where(
                m.LLMCall.purpose == PURPOSE, m.LLMCall.status == "ok"
            )
        )
    ).one()
    return float(mean) if count >= MIN_PILOT_CALLS and mean is not None else None


def cost_estimate(
    contexts: Sequence[ReportContext],
    settings: Settings,
    *,
    batch: bool,
    measured_output_tokens: float | None = None,
) -> CostEstimate:
    """Range from assumed output lengths, or from the pilot's measured mean (±30%)."""
    users = [user_message(c) for c in contexts]
    model = settings.llm_model_extract
    if measured_output_tokens is None:
        return estimate(SYSTEM_PROMPT, users, model=model, batch=batch)
    return estimate(
        SYSTEM_PROMPT,
        users,
        model=model,
        batch=batch,
        output_tokens_low=round(measured_output_tokens * 0.7),
        output_tokens_high=round(measured_output_tokens * 1.3),
    )


async def _link(session: AsyncSession, report_id: int, key: str) -> None:
    await session.execute(
        pg_insert(m.LLMExtraction)
        .values(
            report_id=report_id, prompt_version=PROMPT_VERSION, cache_key=key, rejected_quotes=0
        )
        .on_conflict_do_update(
            index_elements=[m.LLMExtraction.report_id, m.LLMExtraction.prompt_version],
            set_={"cache_key": key},
        )
    )
    await session.commit()


async def run_online(
    session: AsyncSession,
    gateway: LLMGateway,
    contexts: Sequence[ReportContext],
    settings: Settings,
) -> dict[str, float]:
    """Sequential calls (one session); returns counts and the money spent by this run."""
    spent = cached = 0.0
    done = 0
    for ctx in contexts:
        result = await gateway.structured(
            purpose=PURPOSE,
            model=settings.llm_model_extract,
            prompt_version=PROMPT_VERSION,
            system=SYSTEM_PROMPT,
            user=user_message(ctx),
            schema=ReportExtraction,
            effort=settings.llm_effort_extract,
            max_tokens=settings.llm_max_tokens_extract,
        )
        await _link(session, ctx.report_id, result.cache_key)
        spent += result.cost_usd
        cached += result.cached
        done += 1
    return {"reports": done, "from_cache": cached, "spent_usd": round(spent, 4)}


async def run_batch(
    session: AsyncSession,
    runner: BatchRunner,
    contexts: Sequence[ReportContext],
    settings: Settings,
    *,
    estimated_cost_usd: float,
    resume_batch_id: str | None = None,
) -> list[BatchOutcome]:
    by_id = {f"r{c.report_id}": c for c in contexts}
    outcomes = await runner.run(
        purpose=PURPOSE,
        model=settings.llm_model_extract,
        prompt_version=PROMPT_VERSION,
        items=[BatchItem(cid, SYSTEM_PROMPT, user_message(c)) for cid, c in by_id.items()],
        schema=ReportExtraction,
        effort=settings.llm_effort_extract,
        max_tokens=settings.llm_max_tokens_extract,
        estimated_cost_usd=estimated_cost_usd,
        resume_batch_id=resume_batch_id,
    )
    for outcome in outcomes:
        if outcome.status in ("ok", "cached"):
            await _link(session, by_id[outcome.custom_id].report_id, outcome.cache_key)
    return outcomes


async def load_findings(
    session: AsyncSession, contexts: Sequence[ReportContext]
) -> tuple[LLMFindings, int]:
    """Stored LLM results for the current prompt version as hits; also the reports covered."""
    rows = await session.execute(
        select(m.LLMExtraction.report_id, m.LLMResult.output)
        .join(m.LLMResult, m.LLMResult.cache_key == m.LLMExtraction.cache_key)
        .where(m.LLMExtraction.prompt_version == PROMPT_VERSION)
    )
    outputs = dict(rows.tuples().all())
    findings = LLMFindings()
    covered = 0
    for ctx in contexts:
        raw = outputs.get(ctx.report_id)
        if raw is None:
            continue
        try:
            extraction = ReportExtraction.model_validate(raw)
        except ValidationError:
            log.warning("llm_result_invalid", report_id=ctx.report_id)
            continue
        before = findings.rejected_quotes
        findings_from(extraction, ctx, findings)
        covered += 1
        rejected = findings.rejected_quotes - before
        await session.execute(
            update(m.LLMExtraction)
            .where(
                m.LLMExtraction.report_id == ctx.report_id,
                m.LLMExtraction.prompt_version == PROMPT_VERSION,
            )
            .values(rejected_quotes=rejected)
        )
    return findings, covered
