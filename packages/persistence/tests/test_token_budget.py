"""Token accounting survives failed attempts, transaction failure and recovery."""

import asyncio
from datetime import datetime, timedelta
from uuid import UUID

import pytest
from runveil_core.models import (
    ModelRequest,
    ModelResponse,
    ProviderError,
    ProviderErrorCode,
    TokenUsage,
)
from runveil_core.runs import RunStatus
from runveil_core.runtime import ElapsedBudgetExceeded, RuntimeConfig, execute
from runveil_core.scripted import ScriptedProvider
from runveil_core.tools import fixture_registry
from runveil_persistence import execution, jobs
from runveil_persistence.database import create_engine
from runveil_persistence.execution import PostgresExecutionStore, load_runtime_state
from runveil_persistence.history import HistoryRepository
from runveil_persistence.jobs import OwnershipLost, claim_next, enroll
from runveil_persistence.models import JobRow, ModelInvocationRow
from runveil_persistence.repositories import AgentRepository, RunRepository
from runveil_worker.worker import (
    POLICY,
    TOKEN_PROFILE,
    FixtureProvider,
    configuration,
    submit,
    work_once,
)
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def seeded(sessions: async_sessionmaker[AsyncSession]) -> tuple[UUID, RuntimeConfig]:
    config = configuration(TOKEN_PROFILE).model_copy(update={"max_elapsed_seconds": 86400})
    async with sessions.begin() as session:
        agents = AgentRepository(session)
        agent = await agents.create("Token fixture")
        version = await agents.create_version(agent.id, config.model_dump(mode="json"))
        run_id = (await RunRepository(session).create(version.id)).id
        await enroll(session, run_id, task="Public fixture", profile="token-test")
    return run_id, config


async def test_token_profile_retries_across_engines(
    database: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    at: datetime | None = None
    real_now = jobs.database_now

    async def now(session: AsyncSession) -> datetime:
        return at if at is not None else await real_now(session)

    monkeypatch.setattr(jobs, "database_now", now)
    monkeypatch.setattr(execution, "database_now", now)
    sessions = async_sessionmaker(database)
    run_id = await submit(sessions, profile=TOKEN_PROFILE)
    for attempt in range(3):
        restarted = create_engine(database.url)
        try:
            outcome = await work_once(
                async_sessionmaker(restarted), run_id=run_id, profile=TOKEN_PROFILE
            )
        finally:
            await restarted.dispose()
        assert outcome is not None
        state = outcome[1]
        if attempt < 2:
            assert state.tokens.attempts == attempt + 1
            assert state.tokens.unknown_attempts == 0 and state.tokens.input_tokens == 0
            async with sessions.begin() as session:
                job = await session.get(JobRow, run_id)
                assert job is not None
                at = job.available_at
        else:
            assert state.final_result is not None and state.tokens.attempts == 4
            assert (state.tokens.input_tokens, state.tokens.output_tokens) == (20, 10)
    assert await work_once(sessions, run_id=run_id, profile=TOKEN_PROFILE) is None


@pytest.mark.parametrize(
    "case,usage,error",
    [
        ("input", TokenUsage(input_tokens=100, output_tokens=1), "token_limit_exceeded"),
        ("output", TokenUsage(input_tokens=1, output_tokens=101), "token_limit_exceeded"),
        ("partial", TokenUsage(input_tokens=7), "token_usage_unknown"),
        ("rate", TokenUsage(), "token_usage_unknown"),
        ("invalid", TokenUsage(input_tokens=7, output_tokens=3), "invalid_response"),
    ],
)
async def test_token_failure_rejects_action_and_retry(
    database: AsyncEngine, case: str, usage: TokenUsage, error: str
) -> None:
    sessions = async_sessionmaker(database)
    run_id, config = await seeded(sessions)
    claim = await claim_next(sessions, profile="token-test", run_id=run_id)
    assert claim is not None

    class Provider(FixtureProvider):
        async def generate(self, request: ModelRequest) -> ModelResponse:
            if case == "rate":
                raise ProviderError(ProviderErrorCode.RATE_LIMITED)
            response = await super().generate(request)
            return response.model_copy(
                update={
                    "usage": usage,
                    **({"content": "invalid-content-sentinel"} if case == "invalid" else {}),
                }
            )

    state = await execute(
        run_id,
        claim.task,
        provider_name=config.provider,
        provider=Provider(),
        store=PostgresExecutionStore(sessions, claim=claim, expected_config=config),
        tools=fixture_registry(),
        tool_policy=POLICY,
        allow_model_retries=True,
    )
    assert state.error_code == error and state.next_tool is None and state.final_result is None
    assert state.retries_scheduled == 0 and state.tokens.attempts == 1
    assert state.tokens.input_tokens == (usage.input_tokens or 0)
    assert state.tokens.last_usage == usage
    assert state.tokens.unknown_attempts == int(
        usage.output_tokens is None or usage.input_tokens is None
    )
    async with sessions.begin() as session:
        assert await load_runtime_state(session, run_id) == state
        assert (await RunRepository(session).get(run_id)).status == RunStatus.FAILED
        records = list(
            await session.scalars(
                select(ModelInvocationRow).where(ModelInvocationRow.run_id == run_id)
            )
        )
        assert len(records) == 1 and records[0].result is None
        events = await HistoryRepository(session).events(run_id)
        assert not any(event.kind in ("tool.requested", "retry.scheduled") for event in events)
        assert "invalid-content-sentinel" not in state.model_dump_json()
        if error.startswith("token_"):
            assert events[-2].kind == (
                "budget.unknown" if error == "token_usage_unknown" else "budget.exceeded"
            )


async def test_uncertain_intent_and_stale_owner(database: AsyncEngine) -> None:
    sessions = async_sessionmaker(database)
    run_id, config = await seeded(sessions)
    claim = await claim_next(sessions, profile="token-test", run_id=run_id)
    assert claim is not None
    old = PostgresExecutionStore(sessions, claim=claim, expected_config=config)
    started = await old.start(run_id, claim.task, config.provider)
    pending = await old.request(started.cursor, kind="model", payload={}, config=config)
    async with sessions.begin() as session:
        await session.execute(
            text(
                "UPDATE worker_jobs SET expires_at=clock_timestamp() - interval '1 second' "
                "WHERE run_id=:id"
            ),
            {"id": run_id},
        )
    replacement = await claim_next(sessions, profile="token-test", run_id=run_id)
    assert replacement is not None
    with pytest.raises(OwnershipLost):
        await old.complete(pending, started.state, error_code="execution_interrupted")
    provider = ScriptedProvider([])
    state = await execute(
        run_id,
        replacement.task,
        provider_name=config.provider,
        provider=provider,
        store=PostgresExecutionStore(sessions, claim=replacement, expected_config=config),
    )
    assert not provider.requests and state.error_code == "execution_interrupted"
    assert state.tokens.attempts == state.tokens.unknown_attempts == 1


async def test_accounting_rollback_and_late_usage(
    database: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    sessions = async_sessionmaker(database)
    run_id, config = await seeded(sessions)
    claim = await claim_next(sessions, profile="token-test", run_id=run_id)
    assert claim is not None
    store = PostgresExecutionStore(sessions, claim=claim, expected_config=config)
    started = await store.start(run_id, claim.task, config.provider)
    pending = await store.request(started.cursor, kind="model", payload={}, config=config)
    state = started.state.model_copy(
        update={
            "tokens": started.state.tokens.add(TokenUsage(input_tokens=100, output_tokens=4)),
            "steps_used": 1,
            "error_code": "token_limit_exceeded",
        }
    )

    async def interrupt(*args: object, **kwargs: object) -> None:
        raise asyncio.CancelledError

    with monkeypatch.context() as patch:
        patch.setattr(RunRepository, "transition", interrupt)
        with pytest.raises(asyncio.CancelledError):
            await store.complete(pending, state, error_code=state.error_code)
    async with sessions.begin() as session:
        assert await load_runtime_state(session, run_id) == started.state
        record = await session.get(ModelInvocationRow, pending.id)
        assert record is not None and record.status == "REQUESTED"
    # Expire the observed database clock without altering the pinned deadline.

    from runveil_persistence import execution, jobs

    real_now = jobs.database_now

    async def late(session: AsyncSession) -> datetime:
        return await real_now(session) + timedelta(days=2)

    monkeypatch.setattr(execution, "database_now", late)
    with pytest.raises(ElapsedBudgetExceeded) as expired:
        await store.complete(pending, state, error_code=state.error_code)
    assert expired.value.state.error_code == "elapsed_time_exceeded"
    assert expired.value.state.tokens == state.tokens
    async with sessions.begin() as session:
        assert await load_runtime_state(session, run_id) == expired.value.state


async def test_known_failed_usage_is_not_reset_by_retry(
    database: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    sessions = async_sessionmaker(database)
    run_id, config = await seeded(sessions)
    claim = await claim_next(sessions, profile="token-test", run_id=run_id)
    assert claim is not None

    class FailedProvider:
        async def generate(self, request: ModelRequest) -> ModelResponse:
            raise ProviderError(
                ProviderErrorCode.RATE_LIMITED, usage=TokenUsage(input_tokens=60, output_tokens=2)
            )

    first = await execute(
        run_id,
        claim.task,
        provider_name=config.provider,
        provider=FailedProvider(),
        tools=fixture_registry(),
        tool_policy=POLICY,
        store=PostgresExecutionStore(sessions, claim=claim, expected_config=config),
        allow_model_retries=True,
    )
    assert first.tokens.input_tokens == 60 and first.retries_scheduled == 1
    async with sessions.begin() as session:
        job = await session.get(JobRow, run_id)
        assert job is not None
        due = job.available_at

    async def now(session: AsyncSession) -> datetime:
        return due

    monkeypatch.setattr(jobs, "database_now", now)
    monkeypatch.setattr(execution, "database_now", now)
    replacement = await claim_next(sessions, profile="token-test", run_id=run_id)
    assert replacement is not None

    class Provider(FixtureProvider):
        async def generate(self, request: ModelRequest) -> ModelResponse:
            return (await super().generate(request)).model_copy(
                update={"usage": TokenUsage(input_tokens=40, output_tokens=3)}
            )

    state = await execute(
        run_id,
        replacement.task,
        provider_name=config.provider,
        provider=Provider(),
        store=PostgresExecutionStore(sessions, claim=replacement, expected_config=config),
        allow_model_retries=True,
        tools=fixture_registry(),
        tool_policy=POLICY,
    )
    assert state.error_code == "token_limit_exceeded" and state.next_tool is None
    assert state.tokens.attempts == 2 and state.tokens.unknown_attempts == 0
    assert (state.tokens.input_tokens, state.tokens.output_tokens) == (100, 5)
