import asyncio
import json
from pathlib import Path
from uuid import UUID

import pytest
from runveil_core.agents import JsonValue
from runveil_core.errors import InvalidTransition, RevisionConflict
from runveil_core.models import ModelRequest, ModelResponse, ProviderErrorCode
from runveil_core.runs import RunStatus
from runveil_core.runtime import RuntimeConfig, execute
from runveil_core.scripted import ScriptedProvider
from runveil_core.tools import (
    FixtureInput,
    FixtureOutput,
    Permission,
    SideEffect,
    ToolPolicy,
    ToolRegistry,
    TypedTool,
    fixture_registry,
)
from runveil_persistence.database import create_engine
from runveil_persistence.execution import PostgresExecutionStore, load_runtime_state
from runveil_persistence.history import HistoryRepository
from runveil_persistence.invocations import InvocationRepository
from runveil_persistence.repositories import AgentRepository, RunRepository
from runveil_tools.repository import RepositoryAccess, RepositoryTools
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

FIXTURE_POLICY = ToolPolicy(allowed_tools=("fixture.info",), permissions=(Permission.READ,))

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def seed_run(database: AsyncEngine, **settings: JsonValue) -> UUID:
    config = RuntimeConfig(
        tool_policy=FIXTURE_POLICY,
        provider="scripted",
        model="fixture",
        system_prompt="Use fixture data.",
    )
    values = config.model_dump(mode="json") | settings
    async with async_sessionmaker(database).begin() as session:
        agents = AgentRepository(session)
        agent = await agents.create("Runtime fixture")
        version = await agents.create_version(agent.id, values)
        return (await RunRepository(session).create(version.id)).id


def response(*, tool: bool = False, bad_arguments: bool = False) -> ModelResponse:
    content: dict[str, JsonValue] = (
        {
            "action": "tool_call",
            "tool_name": "fixture.info",
            "arguments": {"path": "secret-sentinel"} if bad_arguments else {},
            "decision_summary": "Read fixture metadata.",
        }
        if tool
        else {"action": "finish", "result": {"summary": "Fixture verified.", "artifacts": []}}
    )
    return ModelResponse(
        model="fixture", content=json.dumps(content), finish_reason="stop", latency_ms=0.0
    )


async def test_full_run_reconstructs_without_provider(database: AsyncEngine) -> None:
    run_id = await seed_run(database, max_steps=3)
    # A newer version must not change the configuration pinned by this run.
    async with async_sessionmaker(database).begin() as session:
        run = await RunRepository(session).get(run_id)
        agents = AgentRepository(session)
        pinned = await agents.get_version(run.agent_version_id)
        await agents.create_version(
            pinned.agent_id, pinned.configuration | {"max_steps": 1, "model": "newer"}
        )
    provider = ScriptedProvider([response(tool=True), response()])
    state = await execute(
        run_id,
        "Identify the fixture",
        tools=fixture_registry(),
        tool_policy=FIXTURE_POLICY,
        provider_name="scripted",
        provider=provider,
        store=PostgresExecutionStore(async_sessionmaker(database)),
    )
    assert state.steps_used == 3 and state.final_result is not None
    assert all(request.model == "fixture" for request in provider.requests)
    assert [m.role for m in provider.requests[1].messages] == [
        "system",
        "user",
        "assistant",
        "tool",
    ]
    assert json.loads(provider.requests[1].messages[-1].content) == {
        "project": "Runveil",
        "fixture_version": 1,
    }
    second = create_engine(database.url)
    try:
        async with async_sessionmaker(second).begin() as session:
            assert await load_runtime_state(session, run_id) == state
            assert (await RunRepository(session).get(run_id)).status == RunStatus.SUCCEEDED
            history = HistoryRepository(session)
            steps = await history.steps(run_id)
            assert [s.kind for s in steps] == [
                "runtime.started",
                "model.completed",
                "tool.completed",
                "model.completed",
            ]
            events = await history.events(run_id)
            assert [e.sequence for e in events] == list(range(1, len(events) + 1))
            assert events[-1].kind == "run.transitioned"
            records = InvocationRepository(session)
            model_id = UUID(str(steps[1].details["record_id"]))
            tool = await records.get_tool(run_id, UUID(str(steps[2].details["record_id"])))
            assert tool.model_invocation_id == model_id
            assert tool.result == {"project": "Runveil", "fixture_version": 1}
            assert (await records.get_model(run_id, model_id)).request == provider.requests[
                0
            ].model_dump(mode="json")
    finally:
        await second.dispose()
    with pytest.raises(InvalidTransition):
        await execute(
            run_id,
            "Again",
            tools=fixture_registry(),
            tool_policy=FIXTURE_POLICY,
            provider_name="scripted",
            provider=provider,
            store=PostgresExecutionStore(async_sessionmaker(database)),
        )
    assert len(provider.requests) == 2


@pytest.mark.parametrize("limit,expected_calls,expected_tools", [(1, 1, 0), (2, 1, 1), (3, 2, 1)])
async def test_step_bound_precedes_dispatch(
    database: AsyncEngine,
    limit: int,
    expected_calls: int,
    expected_tools: int,
) -> None:
    run_id = await seed_run(database, max_steps=limit)
    provider = ScriptedProvider([response(tool=True)] * 4)
    state = await execute(
        run_id,
        "Keep reading",
        tools=fixture_registry(),
        tool_policy=FIXTURE_POLICY,
        provider_name="scripted",
        provider=provider,
        store=PostgresExecutionStore(async_sessionmaker(database)),
    )
    assert state.error_code == "step_limit_exceeded" and state.steps_used == limit
    assert len(provider.requests) == expected_calls
    async with async_sessionmaker(database).begin() as session:
        assert (await RunRepository(session).get(run_id)).status == RunStatus.FAILED
        assert await load_runtime_state(session, run_id) == state
        events = await HistoryRepository(session).events(run_id)
        assert sum(e.kind == "tool.requested" for e in events) == expected_tools


@pytest.mark.parametrize(
    "failure",
    ["invalid", "unknown_tool", "denied", "arguments", "provider", "exception", "timeout"],
)
async def test_safe_failure_outcomes(database: AsyncEngine, failure: str) -> None:
    run_id = await seed_run(database, timeout_seconds=0.01)
    item: ModelResponse | ProviderErrorCode = response()
    if failure == "invalid":
        item = response().model_copy(update={"content": "secret-sentinel malformed"})
    elif failure == "unknown_tool":
        item = response(tool=True).model_copy(
            update={"content": response(tool=True).content.replace("fixture.info", "shell.exec")}
        )
    elif failure == "denied":
        item = response(tool=True)
    elif failure == "arguments":
        item = response(tool=True, bad_arguments=True)
    elif failure == "provider":
        item = ProviderErrorCode.RATE_LIMITED

    class Provider(ScriptedProvider):
        async def generate(self, request: ModelRequest) -> ModelResponse:
            if failure == "exception":
                raise RuntimeError("secret-sentinel")
            if failure == "timeout":
                await asyncio.Event().wait()
            return await super().generate(request)

    state = await execute(
        run_id,
        "Check",
        tools=fixture_registry(),
        tool_policy=ToolPolicy() if failure == "denied" else FIXTURE_POLICY,
        provider_name="scripted",
        provider=Provider([item]),
        store=PostgresExecutionStore(async_sessionmaker(database)),
    )
    expected = {
        "invalid": "invalid_response",
        "unknown_tool": "invalid_response",
        "denied": "invalid_response",
        "arguments": "invalid_tool_arguments",
        "provider": "provider_rate_limited",
        "exception": "provider_unavailable",
        "timeout": "provider_timeout",
    }[failure]
    assert state.error_code == expected
    async with async_sessionmaker(database).begin() as session:
        assert (await RunRepository(session).get(run_id)).status == RunStatus.FAILED
        assert await load_runtime_state(session, run_id) == state
        steps = await HistoryRepository(session).steps(run_id)
        record_id = UUID(str(steps[-1].details["record_id"]))
        repo = InvocationRepository(session)
        record = (
            await repo.get_tool(run_id, record_id)
            if failure == "arguments"
            else await repo.get_model(run_id, record_id)
        )
        assert record.error_code == expected and record.result is None
        if failure != "arguments":
            assert "secret-sentinel" not in state.model_dump_json()


@pytest.mark.parametrize("boundary", ["model", "tool"])
@pytest.mark.parametrize("interruption", ["lifecycle", "history", "task"])
async def test_inflight_intent_concurrency_and_cancellation(
    database: AsyncEngine,
    interruption: str,
    boundary: str,
) -> None:
    run_id = await seed_run(database)
    entered, release = asyncio.Event(), asyncio.Event()
    sessions = async_sessionmaker(database)

    class BlockingProvider:
        async def generate(self, request: ModelRequest) -> ModelResponse:
            if boundary == "model":
                entered.set()
                await release.wait()
                return response()
            return response(tool=True)

    async def handler(arguments: FixtureInput) -> FixtureOutput:
        entered.set()
        await release.wait()
        return FixtureOutput()

    registry = ToolRegistry(
        [
            TypedTool(
                name="fixture.info",
                description="Blocking public fixture.",
                input_type=FixtureInput,
                output_type=FixtureOutput,
                handler=handler,
                permission=Permission.READ,
                side_effect=SideEffect.READ_ONLY,
            )
        ]
    )
    task = asyncio.create_task(
        execute(
            run_id,
            "Wait",
            tools=registry,
            tool_policy=FIXTURE_POLICY,
            provider_name="scripted",
            provider=BlockingProvider(),
            store=PostgresExecutionStore(sessions),
        )
    )
    try:
        await asyncio.wait_for(entered.wait(), timeout=5)
        # A second session sees committed intent and can acquire the run lock while
        # the provider/tool waits. This also rejects another executor without dispatch.
        async with sessions.begin() as session:
            await session.execute(text("SET LOCAL lock_timeout = '1s'"))
            history = HistoryRepository(session)
            events = await history.events(run_id)
            assert events[-1].kind == f"{boundary}.requested"
            record_id = UUID(str(events[-1].payload["record_id"]))
            if interruption == "lifecycle":
                await RunRepository(session).transition(
                    run_id, RunStatus.CANCELLED, expected_revision=1
                )
            elif interruption == "history":
                await history.record_step(
                    run_id,
                    kind="other.writer",
                    details={},
                    state={},
                    expected_revision=1,
                    expected_sequence=events[-1].sequence,
                )
        with pytest.raises(InvalidTransition):
            await execute(
                run_id,
                "Duplicate",
                tools=fixture_registry(),
                tool_policy=FIXTURE_POLICY,
                provider_name="scripted",
                provider=ScriptedProvider([]),
                store=PostgresExecutionStore(sessions),
            )
        if interruption == "task":
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
        else:
            release.set()
            with pytest.raises(RevisionConflict):
                await task
        async with sessions.begin() as session:
            repo = InvocationRepository(session)
            get_record = repo.get_model if boundary == "model" else repo.get_tool
            record = await get_record(run_id, record_id)
            assert record.status.value == "REQUESTED" and record.result is None
    finally:
        if not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)


@pytest.mark.parametrize(
    "settings,provider",
    [({"max_steps": 0}, "scripted"), ({}, "wrong"), ({"schema_version": 1}, "scripted")],
)
async def test_invalid_start_has_no_writes(
    database: AsyncEngine,
    settings: dict[str, JsonValue],
    provider: str,
) -> None:
    run_id = await seed_run(database, **settings)
    with pytest.raises(ValueError):
        await execute(
            run_id,
            "Check",
            tools=fixture_registry(),
            tool_policy=FIXTURE_POLICY,
            provider_name=provider,
            provider=ScriptedProvider([]),
            store=PostgresExecutionStore(async_sessionmaker(database)),
        )
    async with async_sessionmaker(database).begin() as session:
        assert (await RunRepository(session).get(run_id)).status == RunStatus.QUEUED
        assert len(await HistoryRepository(session).events(run_id)) == 1


@pytest.mark.parametrize("outcome", ["success", "output", "exception", "timeout"])
async def test_registered_tool_commits_intent_and_atomic_outcome(
    database: AsyncEngine, outcome: str
) -> None:
    policy = ToolPolicy(allowed_tools=("native.info",), permissions=(Permission.READ,))
    run_id = await seed_run(database, tool_policy=policy.model_dump(mode="json"))
    sessions = async_sessionmaker(database)
    calls = 0
    entered, release = asyncio.Event(), asyncio.Event()

    async def handler(arguments: FixtureInput) -> FixtureOutput:
        nonlocal calls
        calls += 1
        entered.set()
        await release.wait()
        if outcome == "exception":
            raise RuntimeError("secret-sentinel")
        if outcome == "output":
            return FixtureOutput.model_construct(project="secret-sentinel")
        return FixtureOutput()

    registry = ToolRegistry(
        [
            TypedTool(
                name="native.info",
                description="Public native fixture.",
                input_type=FixtureInput,
                output_type=FixtureOutput,
                handler=handler,
                permission=Permission.READ,
                side_effect=SideEffect.READ_ONLY,
                timeout_seconds=1.0 if outcome == "timeout" else 5.0,
            )
        ]
    )
    first = response(tool=True)
    first = first.model_copy(
        update={"content": first.content.replace("fixture.info", "native.info")}
    )
    provider = ScriptedProvider([first, response()])
    task = asyncio.create_task(
        execute(
            run_id,
            "Inspect",
            provider_name="scripted",
            provider=provider,
            store=PostgresExecutionStore(sessions),
            tools=registry,
            tool_policy=policy,
        )
    )
    try:
        await asyncio.wait_for(entered.wait(), timeout=5)
        async with sessions.begin() as session:
            # Intent is visible and no transaction holds the run lock during execution.
            await session.execute(text("SET LOCAL lock_timeout = '1s'"))
            await session.execute(
                text("SELECT id FROM runs WHERE id = :id FOR UPDATE"), {"id": run_id}
            )
            events = await HistoryRepository(session).events(run_id)
            requested = next(e for e in events if e.kind == "tool.requested")
            tool_id = UUID(str(requested.payload["record_id"]))
            record = await InvocationRepository(session).get_tool(run_id, tool_id)
            assert record.tool_name == "native.info" and record.status.value == "REQUESTED"
        if outcome != "timeout":
            release.set()
        state = await task
    finally:
        if not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
    expected = {
        "success": None,
        "output": "invalid_tool_output",
        "exception": "tool_failed",
        "timeout": "tool_timeout",
    }[outcome]
    assert state.error_code == expected and calls == 1
    assert "secret-sentinel" not in state.model_dump_json()
    async with sessions.begin() as session:
        assert await load_runtime_state(session, run_id) == state
        record = await InvocationRepository(session).get_tool(run_id, tool_id)
        assert record.error_code == expected
        assert record.model_invocation_id is not None
        run = await RunRepository(session).get(run_id)
        assert run.status == (RunStatus.SUCCEEDED if outcome == "success" else RunStatus.FAILED)
        if outcome == "success":
            assert record.result == {"project": "Runveil", "fixture_version": 1}
            assert provider.requests[1].messages[-1].tool_name == "native.info"
        else:
            assert record.result is None and len(provider.requests) == 1
            events = await HistoryRepository(session).events(run_id)
            assert any(e.kind == "tool.failed" for e in events)


@pytest.mark.parametrize("denied", [False, True])
async def test_repository_search_read_persisted_boundary(
    database: AsyncEngine, tmp_path: Path, denied: bool
) -> None:
    (tmp_path / "public.txt").write_text("Runveil public fixture\n", encoding="utf-8")
    (tmp_path / "private.txt").write_text("not-disclosed-sentinel", encoding="utf-8")
    policy = ToolPolicy(
        allowed_tools=("repository.search", "repository.read_file"), permissions=(Permission.READ,)
    )
    run_id = await seed_run(database, tool_policy=policy.model_dump(mode="json"), max_steps=5)
    search = response(tool=True).model_copy(
        update={
            "content": json.dumps(
                {
                    "action": "tool_call",
                    "tool_name": "repository.search",
                    "arguments": {"query": "Runveil"},
                    "decision_summary": "Locate public source.",
                }
            )
        }
    )
    read = response(tool=True).model_copy(
        update={
            "content": json.dumps(
                {
                    "action": "tool_call",
                    "tool_name": "repository.read_file",
                    "arguments": {"path": "private.txt" if denied else "public.txt"},
                    "decision_summary": "Inspect the file.",
                }
            )
        }
    )
    provider = ScriptedProvider([search, read, response()])
    sessions = async_sessionmaker(database)
    with RepositoryTools(tmp_path, access=RepositoryAccess(files=("public.txt",))) as repository:
        state = await execute(
            run_id,
            "Inspect the public fixture.",
            provider_name="scripted",
            provider=provider,
            store=PostgresExecutionStore(sessions),
            tools=ToolRegistry(repository.bindings()),
            tool_policy=policy,
        )
    async with sessions.begin() as session:
        assert await load_runtime_state(session, run_id) == state
        assert (await RunRepository(session).get(run_id)).status == (
            RunStatus.FAILED if denied else RunStatus.SUCCEEDED
        )
        events = await HistoryRepository(session).events(run_id)
        tool_ids = [UUID(str(e.payload["record_id"])) for e in events if e.kind == "tool.requested"]
        records = [await InvocationRepository(session).get_tool(run_id, id) for id in tool_ids]
        assert [r.tool_name for r in records] == ["repository.search", "repository.read_file"]
        assert all(r.model_invocation_id is not None for r in records)
        assert records[0].result == {
            "matches": [{"path": "public.txt", "line": 1, "excerpt": "Runveil public fixture"}],
            "truncated": False,
            "files_scanned": 1,
        }
        if denied:
            assert state.error_code == records[1].error_code == "tool_permission_denied"
            assert records[1].result is None and len(provider.requests) == 2
        else:
            assert state.final_result is not None and state.steps_used == 5
            assert records[1].result == {
                "path": "public.txt",
                "content": "Runveil public fixture\n",
                "next_offset": None,
            }
            assert json.loads(provider.requests[2].messages[-1].content) == records[1].result
        evidence = json.dumps([r.result for r in records]) + state.model_dump_json()
        assert "not-disclosed-sentinel" not in evidence and str(tmp_path) not in evidence
