"""Run with python -m runveil_worker; prints only IDs, status and fixed errors."""

import argparse
import asyncio
from uuid import UUID

from runveil_persistence.database import create_engine, database_url
from sqlalchemy.ext.asyncio import async_sessionmaker

from runveil_worker.worker import BUDGET_PROFILE, PROFILE, RETRY_PROFILE, submit, work_once


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("submit", "work"))
    parser.add_argument("--once", action="store_true", help="Check for at most one eligible run")
    parser.add_argument("--run-id", type=UUID, help="Select one enrolled run")
    parser.add_argument(
        "--profile", choices=(PROFILE, RETRY_PROFILE, BUDGET_PROFILE), default=PROFILE
    )
    args = parser.parse_args()
    if args.command == "submit" and (args.once or args.run_id):
        parser.error("Worker options apply only to work")
    engine = create_engine(database_url())
    try:
        sessions = async_sessionmaker(engine)
        if args.command == "submit":
            print(f"run_id={await submit(sessions, profile=args.profile)}")
            return 0
        while True:
            outcome = await work_once(sessions, run_id=args.run_id, profile=args.profile)
            if outcome is not None:
                run_id, state = outcome
                status = (
                    "FAILED"
                    if state.error_code
                    else ("SUCCEEDED" if state.final_result else "RETRYING")
                )
                print(
                    f"run_id={run_id} status={status} steps={state.steps_used} "
                    f"retries={state.retries_scheduled}",
                    flush=True,
                )
            if args.once:
                if outcome is None:
                    print("no_eligible_work")
                return 1 if outcome is not None and outcome[1].error_code else 0
            await asyncio.sleep(1)
    finally:
        await engine.dispose()


if __name__ == "__main__":
    try:
        raise SystemExit(asyncio.run(main()))
    except KeyboardInterrupt:
        pass
    except Exception:
        # Never print DB URLs, task content, ownership tokens or raw exceptions.
        print("worker_failed", flush=True)
        raise SystemExit(1) from None
