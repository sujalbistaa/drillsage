"""`drillsage-data`: fetch raw sources, load them, and write the data reports.

drillsage-data fetch       # download pinned DDR mirror + Sodir tables into data/raw
drillsage-data load        # idempotent load into Postgres (run twice: no changes)
drillsage-data fidelity    # parser fidelity report → eval/reports/parser_fidelity.*
drillsage-data qc          # per-wellbore data QC report → eval/reports/data_qc.*
drillsage-data all         # fetch, load, fidelity, qc
"""

import argparse
import asyncio
import json
import logging
import sys
from dataclasses import asdict
from pathlib import Path

from drillsage.core.config import REPO_ROOT, get_settings
from drillsage.core.logging import configure_logging, get_logger
from drillsage.db.session import Database
from drillsage.ingest import reports
from drillsage.ingest.fetch import fetch_all
from drillsage.ingest.pipeline import run_ingest, table_counts

log = get_logger(__name__)

REPORTS_DIR = REPO_ROOT / "eval" / "reports"


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
    parser.add_argument("command", choices=["fetch", "load", "fidelity", "qc", "all"])
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
    return 0


if __name__ == "__main__":
    sys.exit(main())
