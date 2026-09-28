"""`drillsage-data`: fetch raw sources, load them, and write the data reports.

drillsage-data fetch       # download pinned DDR mirror + Sodir tables into data/raw
drillsage-data load        # idempotent load into Postgres (run twice: no changes)
drillsage-data fidelity    # parser fidelity report → eval/reports/parser_fidelity.*
drillsage-data qc          # per-wellbore data QC report → eval/reports/data_qc.*
drillsage-data extract     # rebuild events (rules + stored LLM results; free) + report
drillsage-data llm-estimate --pilot 50                 # cost estimate only, calls no model
drillsage-data llm-extract --pilot 50 --online --yes   # paid: needs --yes, respects budget
drillsage-data llm-extract --all --yes [--resume-batch ID]   # Batches API backfill
drillsage-data gold-sample # stratified gold sample → data/processed/gold/gold-v1.jsonl
drillsage-data gold-eval   # score tiers against eval/gold/labels-gold-v1.json
drillsage-data snapshot    # field snapshot for the web cockpit, from raw files (no database)
drillsage-data all         # fetch, load, fidelity, qc, extract, snapshot (never calls a model)
"""

import argparse
import asyncio
import json
import logging
import sys
from collections import Counter
from dataclasses import asdict
from pathlib import Path

import anthropic

from drillsage.core.config import REPO_ROOT, get_settings
from drillsage.core.logging import configure_logging, get_logger
from drillsage.db.session import Database
from drillsage.evaluation import gold
from drillsage.evaluation import report as gold_report
from drillsage.extract import llm_run
from drillsage.extract import report as extraction_report
from drillsage.extract.pipeline import load_activity_records, run_extraction
from drillsage.field.snapshot import build_snapshot, write_snapshot
from drillsage.ingest import reports
from drillsage.ingest.fetch import fetch_all
from drillsage.ingest.pipeline import run_ingest, table_counts
from drillsage.llm.batch import BatchRunner
from drillsage.llm.factory import make_provider
from drillsage.llm.gateway import LLMGateway
from drillsage.llm.store import SqlLLMStore

log = get_logger(__name__)

REPORTS_DIR = REPO_ROOT / "eval" / "reports"
GOLD_DIR = REPO_ROOT / "eval" / "gold"


async def _load(data_dir: Path, basin_pack: str) -> None:
    database = Database(get_settings())
    try:
        async for session in database.session():
            before = await table_counts(session)
            stats = await run_ingest(session, data_dir, basin_pack)
            after = await table_counts(session)
        changed = {t: (before[t], after[t]) for t in after if before[t] != after[t]}
        print(json.dumps({"stats": asdict(stats), "row_count_changes": changed}, indent=2))  # noqa: T201
    finally:
        await database.dispose()


async def _extract(reports_dir: Path) -> None:
    database = Database(get_settings())
    try:
        async for session in database.session():
            stats = await run_extraction(session)
            payload = await extraction_report.collect(session)
        extraction_report.write(payload, reports_dir)
        print(json.dumps(asdict(stats), indent=2))  # noqa: T201
    finally:
        await database.dispose()


async def _llm(args: argparse.Namespace, reports_dir: Path, *, spend: bool) -> int:
    settings = get_settings()
    database = Database(settings)
    try:
        async for session in database.session():
            records, _ = await load_activity_records(session)
            contexts = await llm_run.load_contexts(session, records)
            chosen = contexts if args.all else llm_run.pilot_sample(contexts, args.pilot)
            online = args.online or settings.llm_provider != "anthropic"  # batches: Anthropic only
            store = SqlLLMStore(session)
            measured = await llm_run.measured_output_tokens(session)
            estimate = llm_run.cost_estimate(
                chosen, settings, batch=not online, measured_output_tokens=measured
            )
            remaining = settings.llm_budget_usd - await store.spent_usd()
            report = {
                "provider": settings.llm_provider,
                "mode": "online" if online else "batch",
                "estimate": asdict(estimate),
                "output_tokens_basis": "pilot" if measured else "assumed range",
                "budget_remaining_usd": round(remaining, 2),
            }
            print(json.dumps(report, indent=2))  # noqa: T201
            if not spend:
                return 0
            if not args.yes:
                log.error("llm_extract_needs_confirmation", hint="re-run with --yes to spend")
                return 2
            summary: object
            if online:
                gateway = LLMGateway(
                    make_provider(settings),
                    store,
                    budget_usd=settings.llm_budget_usd,
                    local_only=settings.local_only,
                )
                summary = await llm_run.run_online(session, gateway, chosen, settings)
            else:
                runner = BatchRunner(
                    anthropic.AsyncAnthropic(max_retries=4),
                    store,
                    budget_usd=settings.llm_budget_usd,
                    local_only=settings.local_only,
                )
                outcomes = await llm_run.run_batch(
                    session,
                    runner,
                    chosen,
                    settings,
                    estimated_cost_usd=estimate.cost_high_usd,
                    resume_batch_id=args.resume_batch,
                )
                summary = dict(Counter(o.status for o in outcomes))
            print(json.dumps({"llm": summary}, indent=2))  # noqa: T201
    finally:
        await database.dispose()
    await _extract(reports_dir)
    return 0


async def _qc(reports_dir: Path) -> None:
    database = Database(get_settings())
    try:
        async for session in database.session():
            payload = await reports.collect_data_qc(session)
        reports.write_data_qc(payload, reports_dir)
    finally:
        await database.dispose()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="drillsage-data", description=__doc__.split("\n")[0])
    parser.add_argument(
        "command",
        choices=[
            "fetch",
            "load",
            "fidelity",
            "qc",
            "extract",
            "llm-estimate",
            "llm-extract",
            "gold-sample",
            "gold-eval",
            "snapshot",
            "all",
        ],
    )
    scope = parser.add_mutually_exclusive_group()
    scope.add_argument("--pilot", type=int, default=50, help="stratified sample of N reports")
    scope.add_argument("--all", action="store_true", help="every daily report")
    parser.add_argument("--online", action="store_true", help="normal calls instead of a batch")
    parser.add_argument("--yes", action="store_true", help="confirm spending money on LLM calls")
    parser.add_argument("--resume-batch", help="collect results of an already submitted batch")
    parser.add_argument("--labels", type=Path, help="gold labels JSON (default eval/gold/...)")
    parser.add_argument(
        "--refresh-sodir", action="store_true", help="re-download Sodir tables even if present"
    )
    parser.add_argument("--data-dir", type=Path, help="override DRILLSAGE_DATA_DIR")
    parser.add_argument("--reports-dir", type=Path, default=REPORTS_DIR, help="report output")
    args = parser.parse_args(argv)

    settings = get_settings()
    configure_logging(level=settings.log_level, json_output=settings.log_json)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    data_dir: Path = (args.data_dir or settings.data_dir).resolve()
    reports_dir: Path = args.reports_dir
    command: str = args.command

    if command in ("fetch", "all"):
        fetch_all(data_dir / "raw", refresh_sodir=bool(args.refresh_sodir))
    if command in ("load", "all"):
        asyncio.run(_load(data_dir, settings.basin_pack))
    if command in ("fidelity", "all"):
        result = reports.write_parser_fidelity(data_dir, reports_dir)
        if result.coverage_pct < 100.0:  # noqa: PLR2004 - the target is exactly 100%
            log.error("parser_fidelity_below_target", coverage_pct=result.coverage_pct)
            return 1
    if command in ("qc", "all"):
        asyncio.run(_qc(reports_dir))
    if command in ("extract", "all"):
        asyncio.run(_extract(reports_dir))
    if command in ("snapshot", "all"):
        snapshot = build_snapshot(data_dir, settings.basin_pack)
        path = write_snapshot(snapshot, data_dir)
        log.info("snapshot_written", path=str(path), events=snapshot.stats.events)
    if command == "gold-sample":
        path = data_dir / "processed" / "gold" / f"{gold.SAMPLE_VERSION}.jsonl"
        gold.write_sample(gold.draw_sample(gold.read_lines(data_dir)), path)
        log.info("gold_sample_written", path=str(path), labelling_tool="eval/labeling/label.html")
    if command == "gold-eval":
        labels_path = args.labels or GOLD_DIR / f"labels-{gold.SAMPLE_VERSION}.json"
        items = gold.draw_sample(gold.read_lines(data_dir))
        payload = gold_report.build(items, gold.read_labels(labels_path), gold.rule_predictors())
        gold_report.write(payload, reports_dir)
        print(json.dumps(payload["coverage"], indent=2))  # noqa: T201
    if command in ("llm-estimate", "llm-extract"):
        return asyncio.run(_llm(args, reports_dir, spend=command == "llm-extract"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
