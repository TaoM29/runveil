"""Run the built-in public calibration suite against a migrated local database."""

import argparse
import asyncio
import sys
from pathlib import Path

from runveil_persistence.database import create_engine, database_url
from sqlalchemy.ext.asyncio import async_sessionmaker

from runveil_evaluations.benchmark import select_suite
from runveil_evaluations.runner import run_calibration
from runveil_evaluations.statistics import statistical_report


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True, help="New local JSON report path")
    parser.add_argument("--suite", choices=("calibration", "code-reading"), default="calibration")
    parser.add_argument("--split", choices=("development", "held-out"), default="development")
    parser.add_argument(
        "--statistics", action="store_true", help="Include paired statistical summaries"
    )
    args = parser.parse_args()
    try:
        suite = select_suite(args.suite, args.split)
    except ValueError:
        parser.error("The calibration suite has no held-out split")
    # Refuse existing files/symlinks before starting database work. Never overwrite evidence.
    with args.output.open("x", encoding="utf-8") as output:
        engine = create_engine(database_url())
        try:
            report = await run_calibration(async_sessionmaker(engine), suite)
            artifact = statistical_report(report) if args.statistics else report
            output.write(artifact.model_dump_json(indent=2) + "\n")
        finally:
            await engine.dispose()
    print(
        f"{suite.name} ({suite.split}): "
        f"{report.baseline_metrics.passed}/{len(suite.cases)} -> "
        f"{report.candidate_metrics.passed}/{len(suite.cases)}"
    )
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
