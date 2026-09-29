"""Offline process-death acceptance in a newly created, disposable PostgreSQL DB."""

import argparse
import asyncio
import os
import re
import signal
import sys
from contextlib import closing
from pathlib import Path
from typing import Literal
from uuid import UUID, uuid4

import boto3
from alembic import command
from alembic.config import Config
from botocore.stub import Stubber
from runveil_core.agents import JsonValue
from runveil_core.runtime import Cursor, Pending, RuntimeConfig, RuntimeState, execute
from runveil_core.tools import fixture_registry
from runveil_persistence.database import create_engine, database_url
from runveil_persistence.execution import PostgresExecutionStore, load_runtime_state
from runveil_persistence.history import HistoryRepository
from runveil_persistence.jobs import claim_next
from runveil_persistence.models import JobRow, ModelInvocationRow, ToolCallRow
from runveil_persistence.repositories import RunRepository
from runveil_worker.sqs import Notification, SqsQueue, consume_once, publish_once
from runveil_worker.worker import CALLS_PROFILE, POLICY, TokenFixtureProvider, configuration, submit
from sqlalchemy import Connection, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

ROOT = Path(__file__).resolve().parents[1]
QUEUE = "https://sqs.us-east-1.amazonaws.com/123456789012/runveil-acceptance"
Mode = Literal["checkpoint", "intent", "deferred", "acknowledged"]


async def barrier() -> None:
    print("committed", flush=True)
    await asyncio.Event().wait()


async def child(mode: Mode, run_id: UUID) -> None:
    url = database_url()
    if not re.fullmatch(r"runveil_acceptance_[0-9a-f]{32}", url.database or ""):
        raise ValueError("Child requires an acceptance database")
    engine = create_engine(url)
    try:
        sessions = async_sessionmaker(engine)
        if mode in ("deferred", "acknowledged"):
            # Wire stubs prevent every AWS call; deletion is expected only after terminal commit.
            with (
                closing(
                    boto3.client(
                        "sqs",
                        region_name="us-east-1",
                        aws_access_key_id="offline",
                        aws_secret_access_key="offline",
                    )
                ) as sdk,
                Stubber(sdk) as stub,
            ):
                receipt = uuid4().hex
                stub.add_response(
                    "receive_message",
                    {
                        "Messages": [
                            {
                                "Body": Notification(run_id=run_id).model_dump_json(),
                                "ReceiptHandle": receipt,
                            }
                        ]
                    },
                    {
                        "QueueUrl": QUEUE,
                        "MaxNumberOfMessages": 1,
                        "WaitTimeSeconds": 10,
                        "VisibilityTimeout": 30,
                    },
                )
                if mode == "acknowledged":
                    stub.add_response(
                        "delete_message", {}, {"QueueUrl": QUEUE, "ReceiptHandle": receipt}
                    )
                assert await consume_once(sessions, SqsQueue(sdk, QUEUE)) == mode
                stub.assert_no_pending_responses()
            print(mode, flush=True)
            return

        class CutStore(PostgresExecutionStore):
            async def request(
                self,
                cursor: Cursor,
                *,
                kind: Literal["model", "tool"],
                payload: dict[str, JsonValue],
                config: RuntimeConfig,
                model_invocation_id: UUID | None = None,
                tool_name: str | None = None,
            ) -> Pending:
                pending = await super().request(
                    cursor,
                    kind=kind,
                    payload=payload,
                    config=config,
                    model_invocation_id=model_invocation_id,
                    tool_name=tool_name,
                )
                if mode == "intent" and kind == "tool":
                    await barrier()
                return pending

            async def complete(
                self,
                pending: Pending,
                state: RuntimeState,
                *,
                result: dict[str, JsonValue] | None = None,
                error_code: str | None = None,
            ) -> Cursor:
                cursor = await super().complete(
                    pending, state, result=result, error_code=error_code
                )
                if mode == "checkpoint" and pending.kind == "tool":
                    await barrier()
                return cursor

        config = configuration(CALLS_PROFILE)
        claim = await claim_next(sessions, profile=CALLS_PROFILE, run_id=run_id)
        assert claim is not None
        await execute(
            run_id,
            claim.task,
            provider_name=config.provider,
            provider=TokenFixtureProvider(2),
            tools=fixture_registry(),
            tool_policy=POLICY,
            store=CutStore(sessions, claim=claim, expected_config=config),
        )
        raise AssertionError("Crash boundary was not reached")
    finally:
        await engine.dispose()


async def start_child(mode: Mode, run_id: UUID, env: dict[str, str]) -> asyncio.subprocess.Process:
    return await asyncio.create_subprocess_exec(
        sys.executable,
        str(Path(__file__).resolve()),
        "--child",
        mode,
        "--run-id",
        str(run_id),
        env=env,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
    )


async def stop(process: asyncio.subprocess.Process) -> None:
    if process.returncode is None:
        try:
            process.kill()
        except ProcessLookupError:
            pass
    await asyncio.wait_for(process.wait(), timeout=5)


async def deliver(
    mode: Literal["deferred", "acknowledged"], run_id: UUID, env: dict[str, str]
) -> None:
    process = await start_child(mode, run_id, env)
    try:
        output, _ = await asyncio.wait_for(process.communicate(), timeout=15)
        assert process.returncode == 0 and output.strip() == mode.encode()
    finally:
        await stop(process)


async def scenario(
    sessions: async_sessionmaker[AsyncSession],
    env: dict[str, str],
    mode: Literal["checkpoint", "intent"],
) -> None:
    run_id = await submit(sessions, profile=CALLS_PROFILE, queue_url=QUEUE)
    with (
        closing(
            boto3.client(
                "sqs",
                region_name="us-east-1",
                aws_access_key_id="offline",
                aws_secret_access_key="offline",
            )
        ) as sdk,
        Stubber(sdk) as stub,
    ):
        stub.add_response(
            "send_message",
            {"MessageId": "offline-publication"},
            {
                "QueueUrl": QUEUE,
                "MessageBody": Notification(run_id=run_id).model_dump_json(),
            },
        )
        assert await publish_once(sessions, SqsQueue(sdk, QUEUE))
        stub.assert_no_pending_responses()
    process = await start_child(mode, run_id, env)
    try:
        assert process.stdout is not None
        assert await asyncio.wait_for(process.stdout.readline(), timeout=15) == b"committed\n"
        # Actual process death, with no Python finally blocks or graceful shutdown.
        await stop(process)
        assert process.returncode == -signal.SIGKILL
    finally:
        await stop(process)
    async with sessions() as session:
        state = await load_runtime_state(session, run_id)
        assert state is not None and state.steps_used == (2 if mode == "checkpoint" else 1)
        tool = (
            await session.scalars(select(ToolCallRow).where(ToolCallRow.run_id == run_id))
        ).one()
        tool_id, result_before = tool.id, tool.result
        assert tool.status == ("SUCCEEDED" if mode == "checkpoint" else "REQUESTED")
        history_before = await HistoryRepository(session).events(run_id)
        job = await session.get(JobRow, run_id)
        assert job is not None and job.deadline_at is not None
        deadline = job.deadline_at
    await deliver("deferred", run_id, env)
    async with sessions.begin() as session:
        assert await HistoryRepository(session).events(run_id) == history_before
        # Only this owned disposable DB, only after verified child death. Avoid an 11-minute wait.
        await session.execute(
            text("UPDATE worker_jobs SET expires_at=clock_timestamp() WHERE run_id=:id"),
            {"id": run_id},
        )
    await deliver("acknowledged", run_id, env)
    async with sessions() as session:
        state = await load_runtime_state(session, run_id)
        run = await RunRepository(session).get(run_id)
        models = list(
            await session.scalars(
                select(ModelInvocationRow).where(ModelInvocationRow.run_id == run_id)
            )
        )
        tool = (
            await session.scalars(select(ToolCallRow).where(ToolCallRow.run_id == run_id))
        ).one()
        job = await session.get(JobRow, run_id)
        assert job is not None and job.deadline_at == deadline
        assert state is not None and tool.id == tool_id
        if mode == "checkpoint":
            assert run.status == "SUCCEEDED" and state.final_result is not None
            assert state.steps_used == 3 and len(models) == 2 and tool.result == result_before
            assert state.tokens.input_tokens == 20 and state.tokens.output_tokens == 10
            assert state.cost is not None and state.cost.known_nanousd == 50_000
        else:
            assert run.status == "FAILED" and state.error_code == "execution_interrupted"
            assert state.steps_used == 2 and len(models) == 1
            assert tool.status == "FAILED" and tool.result is None
        completed_history = await HistoryRepository(session).events(run_id)
        assert completed_history[: len(history_before)] == history_before
    await deliver("acknowledged", run_id, env)
    async with sessions() as session:
        assert await HistoryRepository(session).events(run_id) == completed_history
        assert await load_runtime_state(session, run_id) == state
    print(
        f"PASS {mode}: SIGKILL -> {run.status} steps={state.steps_used} "
        f"error={state.error_code}; active-lease deferral and duplicate acknowledgement",
        flush=True,
    )


def migrate(connection: Connection) -> None:
    config = Config(str(ROOT / "alembic.ini"))
    config.attributes["connection"] = connection
    command.upgrade(config, "head")


async def acceptance() -> None:
    if os.name != "posix":
        raise ValueError("Process-death acceptance requires POSIX")
    raw = os.environ.get("RUNVEIL_TEST_DATABASE_URL")
    if not raw:
        raise ValueError("RUNVEIL_TEST_DATABASE_URL is required")
    admin_url = database_url(raw)
    admin = create_engine(admin_url).execution_options(isolation_level="AUTOCOMMIT")
    name = f"runveil_acceptance_{uuid4().hex}"
    url = admin_url.set(database=name)
    engine = create_engine(url)
    created = False
    try:
        async with admin.connect() as connection:
            await connection.execute(text(f'CREATE DATABASE "{name}"'))
        created = True
        async with engine.begin() as connection:
            await connection.run_sync(migrate)
        # Pass the DB URL only via environment, never command arguments or output.
        env = dict(os.environ, DATABASE_URL=url.render_as_string(hide_password=False))
        sessions = async_sessionmaker(engine)
        for mode in ("checkpoint", "intent"):
            await scenario(sessions, env, mode)
    finally:
        await engine.dispose()
        if created:
            async with admin.connect() as connection:
                await connection.execute(text(f'DROP DATABASE "{name}" WITH (FORCE)'))
        await admin.dispose()
    print("PASS disposable database removed; no live AWS/provider calls", flush=True)


async def main() -> None:
    if not __debug__:
        raise ValueError("Acceptance assertions require normal Python execution")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--child",
        choices=("checkpoint", "intent", "deferred", "acknowledged"),
        help=argparse.SUPPRESS,
    )
    parser.add_argument("--run-id", type=UUID, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.child is None and args.run_id is None:
        await acceptance()
    elif args.child is not None and args.run_id is not None:
        await child(args.child, args.run_id)
    else:
        parser.error("Internal child arguments must be paired")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        raise SystemExit(130) from None
    except Exception:
        print("FAIL phase5_acceptance", flush=True)
        raise SystemExit(1) from None
