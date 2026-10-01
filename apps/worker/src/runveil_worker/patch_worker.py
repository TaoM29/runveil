"""Explicit single-file patch profile; prior review-only approvals are never adopted."""

import argparse
import asyncio
import json
from pathlib import Path
from uuid import UUID

from runveil_core.mutations import APPLY_TOOL, PATCH_PROFILE
from runveil_core.runtime import RuntimeConfig, RuntimeState, execute
from runveil_core.tools import Permission, ToolPolicy, ToolRegistry
from runveil_persistence.approvals import ApprovalRepository
from runveil_persistence.database import create_engine, database_url
from runveil_persistence.execution import PostgresExecutionStore
from runveil_persistence.jobs import claim_next, enroll
from runveil_persistence.models import JobRow, ToolCallRow
from runveil_persistence.repositories import AgentRepository, RunRepository
from runveil_persistence.worker_approvals import resolve_worker_review
from runveil_tools.patch import SingleFileWriter, patch_identity
from runveil_tools.repository import ReadFileOutput, RepositoryAccess, RepositoryTools
from runveil_tools.review import proposal_binding
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from runveil_worker.review_worker import POLICY as READ_POLICY
from runveil_worker.review_worker import ReviewProvider, review_configuration
from runveil_worker.telemetry import telemetry

POLICY = ToolPolicy(
    allowed_tools=(*READ_POLICY.allowed_tools, APPLY_TOOL),
    permissions=(Permission.READ, Permission.WRITE),
)
TASK = (
    "Read the disclosed file, propose the fixed review marker, and apply only after human approval."
)


def patch_configuration(repository: RepositoryTools) -> RuntimeConfig:
    if len(repository.files) != 1 or "/" in repository.files[0]:
        raise ValueError("Patch profile requires one top-level file")
    base = review_configuration(repository)
    assert base.workspace is not None and base.pricing is not None
    return RuntimeConfig.model_validate(
        base.model_dump()
        | {
            "schema_version": 11,
            "workspace": patch_identity(base.workspace),
            "tool_policy": POLICY,
            "provider": "scripted-repository-patch-v1",
            "system_prompt": TASK,
            "pricing": base.pricing.model_copy(update={"provider": "scripted-repository-patch-v1"}),
            "max_model_calls": 2,
            "max_tool_calls": 3,
        }
    )


async def submit_patch(sessions: async_sessionmaker[AsyncSession], root: Path, path: str) -> UUID:
    with await asyncio.to_thread(
        RepositoryTools, root, access=RepositoryAccess(files=(path,)), snapshot=True
    ) as repository:
        config = patch_configuration(repository)
        read = ReadFileOutput.model_validate(await repository.bindings()[0].invoke({"path": path}))
        if read.next_offset is not None:
            raise ValueError("Patch fixture requires at most 4096 characters")
        async with sessions.begin() as session:
            agents = AgentRepository(session)
            agent = await agents.create("Controlled approved patch demonstration")
            version = await agents.create_version(agent.id, config.model_dump(mode="json"))
            run = await RunRepository(session).create(version.id)
            await enroll(session, run.id, task=TASK, profile=PATCH_PROFILE)
            return run.id


async def work_patch_once(
    sessions: async_sessionmaker[AsyncSession],
    root: Path,
    path: str,
    *,
    run_id: UUID,
    allow_write: bool = False,
) -> RuntimeState | None:
    claim = await claim_next(sessions, profile=PATCH_PROFILE, run_id=run_id)
    if claim is None:
        return None
    async with sessions() as session:
        run = await RunRepository(session).get(run_id)
        version = await AgentRepository(session).get_version(run.agent_version_id)
        pinned = RuntimeConfig.model_validate_json(version.configuration_json)
        pending = await session.scalar(
            select(ToolCallRow.id).where(
                ToolCallRow.run_id == run_id,
                ToolCallRow.tool_name == APPLY_TOOL,
                ToolCallRow.status == "REQUESTED",
            )
        )
    if pending is not None:
        # Only terminate uncertain work; never construct a writer or inspect current bytes.
        return await PostgresExecutionStore(
            sessions, claim=claim, expected_config=pinned
        ).fail_uncertain_patch()
    with await asyncio.to_thread(
        RepositoryTools, root, access=RepositoryAccess(files=(path,)), snapshot=True
    ) as repository:
        config = patch_configuration(repository)
        assert config.workspace is not None
        return await execute(
            run_id,
            claim.task,
            provider_name=config.provider,
            provider=ReviewProvider(path),
            tools=ToolRegistry((*repository.bindings(), proposal_binding(repository))),
            tool_policy=POLICY if allow_write else READ_POLICY,
            patch_writer=SingleFileWriter(root, path, config.workspace),
            store=PostgresExecutionStore(sessions, claim=claim, expected_config=config),
        )


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("submit", "work", "inspect", "approve", "reject"))
    parser.add_argument("--run-id", type=UUID)
    parser.add_argument("--repository-root", type=Path)
    parser.add_argument("--file")
    parser.add_argument("--allow-write", action="store_true")
    parser.add_argument("--expected-revision", type=int)
    parser.add_argument("--expected-digest")
    args = parser.parse_args()
    if (args.command == "submit") != (args.run_id is None):
        parser.error("Only submit omits --run-id")
    if args.command in ("submit", "work"):
        if args.repository_root is None or args.file is None:
            parser.error("Submission/work require a root and file")
    elif args.repository_root is not None or args.file is not None:
        parser.error("Workspace applies only to submission/work")
    if args.allow_write and args.command != "work":
        parser.error("Write grant applies only to work")
    deciding = args.command in ("approve", "reject")
    if deciding:
        if args.expected_revision is None or args.expected_digest is None:
            parser.error("Decision requires inspected revision/digest")
    elif args.expected_revision is not None or args.expected_digest is not None:
        parser.error("Expected values apply only to decisions")
    engine = create_engine(database_url())
    try:
        sessions = async_sessionmaker(engine)
        if args.command == "submit":
            assert args.repository_root is not None and args.file is not None
            run_id = await submit_patch(sessions, args.repository_root, args.file)
            print(json.dumps({"run_id": str(run_id)}))
        elif args.command == "work":
            assert args.repository_root is not None and args.file is not None
            result = await work_patch_once(
                sessions,
                args.repository_root,
                args.file,
                run_id=args.run_id,
                allow_write=args.allow_write,
            )
            print(
                json.dumps(
                    {
                        "selected": result is not None,
                        "error_code": result.error_code if result else None,
                    }
                )
            )
        else:
            async with sessions.begin() as session:
                job = await session.get(JobRow, args.run_id)
                if job is None or job.profile != PATCH_PROFILE:
                    raise ValueError("Not a patch run")
                if deciding:
                    assert args.expected_revision is not None and args.expected_digest is not None
                    await resolve_worker_review(
                        session,
                        args.run_id,
                        decision="APPROVED" if args.command == "approve" else "REJECTED",
                        expected_revision=args.expected_revision,
                        expected_digest=args.expected_digest,
                        profile=PATCH_PROFILE,
                    )
                request = await ApprovalRepository(session).get(args.run_id)
                run = await RunRepository(session).get(args.run_id)
                version = await AgentRepository(session).get_version(run.agent_version_id)
                config = RuntimeConfig.model_validate_json(version.configuration_json)
                call = await session.scalar(
                    select(ToolCallRow).where(
                        ToolCallRow.run_id == run.id, ToolCallRow.tool_name == APPLY_TOOL
                    )
                )
                output = {
                    "request": request.model_dump(mode="json"),
                    "run_status": run.status,
                    "run_revision": run.revision,
                    "workspace": config.workspace.model_dump() if config.workspace else None,
                    "mutation": {"status": call.status, "error_code": call.error_code}
                    if call
                    else None,
                }
            print(json.dumps(output, sort_keys=True))
        return 0
    finally:
        await engine.dispose()


if __name__ == "__main__":
    try:
        with telemetry():
            raise SystemExit(asyncio.run(main()))
    except KeyboardInterrupt:
        raise SystemExit(130) from None
    except Exception:
        print("patch_failed")
        raise SystemExit(1) from None
