"""Local durable patch-review demo and operator decisions. Never applies a patch."""

import argparse
import asyncio
import json
from uuid import UUID

from runveil_core.approvals import REVIEW_CONFIGURATION, PatchProposal
from runveil_persistence.approvals import ApprovalRepository
from runveil_persistence.database import create_engine, database_url
from runveil_persistence.repositories import AgentRepository, RunRepository
from sqlalchemy.ext.asyncio import async_sessionmaker


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("demo", "inspect", "approve", "reject"))
    parser.add_argument("--run-id", type=UUID)
    parser.add_argument("--expected-revision", type=int)
    parser.add_argument("--expected-digest")
    args = parser.parse_args()
    deciding = args.command in ("approve", "reject")
    if (args.command == "demo") != (args.run_id is None):
        parser.error("Only demo omits --run-id")
    if deciding:
        if args.expected_revision is None or args.expected_digest is None:
            parser.error(
                "Decision requires --expected-revision and --expected-digest from inspection"
            )
    elif args.expected_revision is not None or args.expected_digest is not None:
        parser.error("Expected revision/digest apply only to decisions")
    engine = create_engine(database_url())
    try:
        async with async_sessionmaker(engine).begin() as session:
            approvals = ApprovalRepository(session)
            if args.command == "demo":
                agents = AgentRepository(session)
                agent = await agents.create("Offline patch review")
                version = await agents.create_version(agent.id, REVIEW_CONFIGURATION)
                run = await RunRepository(session).create(version.id)
                request = await approvals.request(
                    run.id, PatchProposal(path="example.txt", before="before\n", after="after\n")
                )
            elif deciding:
                assert args.expected_revision is not None and args.expected_digest is not None
                request = await approvals.resolve(
                    args.run_id,
                    decision="APPROVED" if args.command == "approve" else "REJECTED",
                    expected_revision=args.expected_revision,
                    expected_digest=args.expected_digest,
                )
            else:
                request = await approvals.get(args.run_id)
            run = await RunRepository(session).get(request.run_id)
            version = await AgentRepository(session).get_version(run.agent_version_id)
            if version.configuration != REVIEW_CONFIGURATION:
                raise ValueError("Not a standalone review run")
            output = {
                "request": request.model_dump(mode="json"),
                "run_status": run.status.value,
                "run_revision": run.revision,
                "patch_applied": False,
            }
        # Do not print success until the transaction commits.
        print(json.dumps(output, sort_keys=True))
        return 0
    finally:
        await engine.dispose()


if __name__ == "__main__":
    try:
        raise SystemExit(asyncio.run(main()))
    except KeyboardInterrupt:
        raise SystemExit(130) from None
    except Exception:
        print("approval_failed")
        raise SystemExit(1) from None
