"""Run the built-in public calibration suite against a migrated local database."""

import argparse
import asyncio
import sys
from pathlib import Path

from runveil_persistence.database import create_engine, database_url
from sqlalchemy.ext.asyncio import async_sessionmaker

from runveil_evaluations.runner import run_calibration


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True, help="New local JSON report path")
    args = parser.parse_args()
    # Refuse existing files/symlinks before starting database work. Never overwrite evidence.
    with args.output.open("x", encoding="utf-8") as output:
        engine = create_engine(database_url())
        try:
            report = await run_calibration(async_sessionmaker(engine))
            output.write(report.model_dump_json(indent=2) + "\n")
        finally:
            await engine.dispose()
    print(f"Calibration: {report.baseline_metrics.passed}/3 -> {report.candidate_metrics.passed}/3")
    return 0


if __name__ == "__main__":
    try:
        code = asyncio.run(main())
    except (Exception, KeyboardInterrupt):
        # No raw database credentials, paths, payloads or exception details on stderr.
        print(
            "Evaluation aborted; no complete report is guaranteed. Inspect durable runs.",
            file=sys.stderr,
        )
        code = 1
    raise SystemExit(code)
