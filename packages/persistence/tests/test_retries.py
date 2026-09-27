"""Persisted retry scheduling, recovery, boundedness and conservative failures."""

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from runveil_core.errors import InvalidTransition
from runveil_core.models import ModelResponse, ProviderErrorCode
from runveil_core.runs import RunStatus
from runveil_core.runtime import ModelRetryPolicy, execute
from runveil_core.scripted import ScriptedProvider
from runveil_core.tools import fixture_registry
from runveil_persistence import execution, jobs
from runveil_persistence.database import create_engine
from runveil_persistence.execution import PostgresExecutionStore, load_runtime_state
from runveil_persistence.history import HistoryRepository
from runveil_persistence.jobs import OwnershipLost, claim_next, enroll
from runveil_persistence.models import JobRow, ModelInvocationRow
from runveil_persistence.repositories import AgentRepository, RunRepository
from runveil_worker.worker import POLICY, RETRY_PROFILE, configuration, submit, work_once
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


@dataclass
class Clock:
    at: datetime

    async def now(self, session: AsyncSession) -> datetime:
        return self.at

    def advance(self, seconds: int) -> None:
        self.at += timedelta(seconds=seconds)


@pytest.fixture
def clock(monkeypatch: pytest.MonkeyPatch) -> Clock:
    # Only the scheduling/lease database-clock seam is controlled. No sleeps.
    clock = Clock(datetime.now(UTC) + timedelta(days=1))
    monkeypatch.setattr(jobs, "database_now", clock.now)
    monkeypatch.setattr(execution, "database_now", clock.now)
    return clock


async def test_backoff_restart_and_attempt_provenance(database: AsyncEngine, clock: Clock) -> None:
    sessions = async_sessionmaker(database)
    run_id = await submit(sessions, profile=RETRY_PROFILE)
    for count, delay in ((1, 1), (2, 2)):
        restarted = create_engine(database.url)
        try:
            outcome = await work_once(
                async_sessionmaker(restarted), run_id=run_id, profile=RETRY_PROFILE
            )
        finally:
            await restarted.dispose()
        assert outcome is not None
        assert outcome[1].retries_scheduled == count and outcome[1].steps_used == count
        assert outcome[1].error_code is None and outcome[1].final_result is None
        async with sessions.begin() as session:
            job = await session.get(JobRow, run_id)
            assert job is not None and job.token is None and job.expires_at is None
            assert job.available_at == clock.at + timedelta(seconds=delay)
            assert (await RunRepository(session).get(run_id)).status == RunStatus.RETRYING
        assert await work_once(sessions, run_id=run_id, profile=RETRY_PROFILE) is None
        clock.advance(delay)
    outcome = await work_once(sessions, run_id=run_id, profile=RETRY_PROFILE)
    assert outcome is not None and outcome[1].final_result is not None
    assert outcome[1].steps_used == 5 and outcome[1].retries_scheduled == 2
    assert outcome[1].retry_source_id is None
    assert await work_once(sessions, run_id=run_id, profile=RETRY_PROFILE) is None
    async with sessions.begin() as session:
        models = list(
            await session.scalars(
                select(ModelInvocationRow)
                .where(ModelInvocationRow.run_id == run_id)
                .order_by(ModelInvocationRow.requested_event_sequence)
            )
        )
        assert [model.status for model in models] == ["FAILED", "FAILED", "SUCCEEDED", "SUCCEEDED"]
        assert models[0].request == models[1].request == models[2].request
        assert models[0].result is None and models[1].result is None
        events = await HistoryRepository(session).events(run_id)
        requests = [event for event in events if event.kind == "model.requested"]
        assert requests[1].payload["retry_of"] == str(models[0].id)
        assert requests[2].payload["retry_of"] == str(models[1].id)
        assert "retry_of" not in requests[0].payload and "retry_of" not in requests[3].payload
        assert [event.sequence for event in events] == list(range(1, len(events) + 1))
        assert await load_runtime_state(session, run_id) == outcome[1]


@pytest.mark.parametrize(
    "boundary",
    [
        "retry_limit",
        "step_limit",
        "step_after_retry",
        "timeout",
        "unavailable",
        "invalid",
        "operator",
    ],
)
async def test_retry_limits_and_non_retryable_failures(
    database: AsyncEngine, clock: Clock, boundary: str
) -> None:
    sessions = async_sessionmaker(database)
    config = configuration(RETRY_PROFILE).model_copy(
        update={
            "model_retry": ModelRetryPolicy(max_retries=2 if boundary == "step_after_retry" else 1),
            "max_steps": {"step_limit": 1, "step_after_retry": 2}.get(boundary, 5),
        }
    )
    async with sessions.begin() as session:
        agents = AgentRepository(session)
        agent = await agents.create("Retry boundary fixture")
        version = await agents.create_version(agent.id, config.model_dump(mode="json"))
        run_id = (await RunRepository(session).create(version.id)).id
        await enroll(session, run_id, task="Public fixture", profile="retry-boundary-v1")
    error = {
        "timeout": ProviderErrorCode.TIMEOUT,
        "unavailable": ProviderErrorCode.UNAVAILABLE,
        "invalid": ProviderErrorCode.INVALID_RESPONSE,
    }.get(boundary, ProviderErrorCode.RATE_LIMITED)
    item = (
        ModelResponse(model="fixture-v1", content="malformed", finish_reason="stop", latency_ms=0.0)
        if boundary == "invalid"
        else error
    )
    provider = ScriptedProvider([item, item])
    attempts = 2 if boundary in ("retry_limit", "step_after_retry") else 1
    for _ in range(attempts):
        claim = await claim_next(sessions, profile="retry-boundary-v1", run_id=run_id)
        assert claim is not None
        state = await execute(
            run_id,
            claim.task,
            provider_name=config.provider,
            provider=provider,
            tools=fixture_registry(),
            tool_policy=POLICY,
            store=PostgresExecutionStore(sessions, claim=claim, expected_config=config),
            allow_model_retries=boundary != "operator",
        )
        clock.advance(1)
    assert state.error_code == error.value
    assert state.steps_used == len(provider.requests) == attempts
    assert state.retries_scheduled == (attempts - 1)
    async with sessions.begin() as session:
        assert (await RunRepository(session).get(run_id)).status == RunStatus.FAILED
    assert await claim_next(sessions, profile="retry-boundary-v1", run_id=run_id) is None


async def test_retry_schedule_rollback_stale_owner_and_cancellation(
    database: AsyncEngine, clock: Clock, monkeypatch: pytest.MonkeyPatch
) -> None:
    sessions = async_sessionmaker(database)
    run_id = await submit(sessions, profile=RETRY_PROFILE)
    claim = await claim_next(sessions, profile=RETRY_PROFILE, run_id=run_id)
    assert claim is not None
    store = PostgresExecutionStore(
        sessions, claim=claim, expected_config=configuration(RETRY_PROFILE)
    )
    started = await store.start(run_id, claim.task, configuration(RETRY_PROFILE).provider)
    pending = await store.request(started.cursor, kind="model", payload={}, config=started.config)
    state = started.state.model_copy(
        update={
            "steps_used": 1,
            "retries_scheduled": 1,
            "retry_source_id": pending.id,
        }
    )

    async def interrupted_transition(
        self: RunRepository,
        run_id: UUID,
        target: RunStatus,
        *,
        expected_revision: int,
        expected_sequence: int | None = None,
    ) -> object:
        raise asyncio.CancelledError

    with monkeypatch.context() as patch:
        patch.setattr(RunRepository, "transition", interrupted_transition)
        with pytest.raises(asyncio.CancelledError):
            await store.schedule_retry(pending, state, error_code="provider_rate_limited")
    async with sessions.begin() as session:
        record = await session.get(ModelInvocationRow, pending.id)
        assert record is not None and record.status == "REQUESTED"
        assert await load_runtime_state(session, run_id) == started.state
        assert (await RunRepository(session).get(run_id)).status == RunStatus.RUNNING
    await store.schedule_retry(pending, state, error_code="provider_rate_limited")
    with pytest.raises(OwnershipLost):
        await store.schedule_retry(pending, state, error_code="provider_rate_limited")
    clock.advance(1)
    # Only one new owner can claim the due retry.
    claims = await asyncio.gather(
        *(claim_next(sessions, profile=RETRY_PROFILE, run_id=run_id) for _ in range(2))
    )
    owners = [owner for owner in claims if owner is not None]
    assert len(owners) == 1 and owners[0].token != claim.token
    async with sessions.begin() as session:
        run = await RunRepository(session).get(run_id)
        await RunRepository(session).transition(
            run_id, RunStatus.CANCELLED, expected_revision=run.revision
        )
    assert await work_once(sessions, run_id=run_id, profile=RETRY_PROFILE) is None
    with pytest.raises(InvalidTransition):
        await PostgresExecutionStore(sessions, claim=owners[0]).start(
            run_id, claim.task, started.config.provider
        )


@pytest.mark.parametrize("after_intent", [False, True])
async def test_restart_after_retry_resume_and_uncertain_dispatch(
    database: AsyncEngine, clock: Clock, after_intent: bool
) -> None:
    sessions = async_sessionmaker(database)
    run_id = await submit(sessions, profile=RETRY_PROFILE)
    await work_once(sessions, run_id=run_id, profile=RETRY_PROFILE)
    clock.advance(1)
    claim = await claim_next(sessions, profile=RETRY_PROFILE, run_id=run_id)
    assert claim is not None
    config = configuration(RETRY_PROFILE)
    store = PostgresExecutionStore(sessions, claim=claim, expected_config=config)
    clock.advance(-1)
    with pytest.raises(ValueError, match="not yet due"):
        await store.start(run_id, claim.task, config.provider)
    clock.advance(1)
    started = await store.start(run_id, claim.task, config.provider)
    denied_provider = ScriptedProvider([])
    with pytest.raises(ValueError, match="operator retry grant"):
        await execute(
            run_id,
            claim.task,
            provider_name=config.provider,
            provider=denied_provider,
            store=store,
        )
    assert not denied_provider.requests
    async with sessions.begin() as session:
        source = await session.get(ModelInvocationRow, started.state.retry_source_id)
        assert source is not None
        original_request = source.request
    # A changed retry request is rejected before creating any intent.
    with pytest.raises(ValueError, match="Retry"):
        await store.request(started.cursor, kind="model", payload={}, config=config)
    if after_intent:
        await store.request(started.cursor, kind="model", payload=original_request, config=config)
    clock.advance(jobs.LEASE_SECONDS)
    restarted = create_engine(database.url)
    try:
        outcome = await work_once(
            async_sessionmaker(restarted), run_id=run_id, profile=RETRY_PROFILE
        )
    finally:
        await restarted.dispose()
    assert outcome is not None
    assert outcome[1].steps_used == 2
    if after_intent:
        assert outcome[1].error_code == "execution_interrupted"
        assert outcome[1].retries_scheduled == 1
    else:
        assert outcome[1].error_code is None and outcome[1].retries_scheduled == 2
