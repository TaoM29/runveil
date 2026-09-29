"""Local operator inspection and verified release; no broker or model calls."""

import argparse
import asyncio
import json
from dataclasses import asdict
from uuid import UUID

from runveil_persistence.admission import inspect_admission, release_quarantine
from runveil_persistence.database import create_engine, database_url
from sqlalchemy.ext.asyncio import async_sessionmaker

from runveil_worker.worker import CALLS_PROFILE, configuration


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("inspect", "release"))
    parser.add_argument("--run-id", required=True, type=UUID)
    parser.add_argument("--expected-revision", type=int)
    args = parser.parse_args()
    if args.command == "release" and (args.expected_revision is None or args.expected_revision < 1):
        parser.error("Release requires a positive --expected-revision from inspection")
    if args.command == "inspect" and args.expected_revision is not None:
        parser.error("Expected revision applies only to release")
    engine = create_engine(database_url())
    try:
        sessions = async_sessionmaker(engine)
        if args.command == "inspect":
            status = await inspect_admission(sessions, args.run_id)
        else:
            status = await release_quarantine(
                sessions,
                args.run_id,
                expected_revision=args.expected_revision,
                profile=CALLS_PROFILE,
                expected_config=configuration(CALLS_PROFILE),
            )
        print(json.dumps(asdict(status), default=str, sort_keys=True))
        return 0
    finally:
        await engine.dispose()


if __name__ == "__main__":
    try:
        raise SystemExit(asyncio.run(main()))
    except KeyboardInterrupt:
        raise SystemExit(130) from None
    except Exception:
        print("admission_failed")
        raise SystemExit(1) from None
