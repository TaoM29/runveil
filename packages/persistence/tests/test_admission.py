"""Bounded preflight rejection, operator release and unchanged runtime evidence."""

import asyncio
from contextlib import closing
from typing import Literal
from uuid import UUID

import boto3
import pytest
from botocore.stub import Stubber
from runveil_core.agents import JsonValue
from runveil_core.errors import InvalidTransition, RevisionConflict
from runveil_core.runs import RunStatus
from runveil_core.runtime import Cursor, Pending, RuntimeConfig, Started, execute
from runveil_core.tools import fixture_registry
from runveil_persistence import admission
from runveil_persistence.admission import (
    inspect_admission,
    record_configuration_rejection,
    release_quarantine,
)
from runveil_persistence.execution import (
    ConfigurationRejected,
    PostgresExecutionStore,
    load_runtime_state,
)
from runveil_persistence.history import HistoryRepository
from runveil_persistence.jobs import OwnershipLost, claim_next, enroll
from runveil_persistence.models import AdmissionEventRow, JobRow, ModelInvocationRow
from runveil_persistence.outbox import claim_publication
from runveil_persistence.repositories import AgentRepository, RunRepository
from runveil_worker import worker
from runveil_worker.sqs import Notification, SqsQueue, consume_once
from runveil_worker.worker import (
    CALLS_PROFILE,
    POLICY,
    TokenFixtureProvider,
    configuration,
    submit,
    work_once,
)
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]
URL = "https://sqs.us-east-1.amazonaws.com/123456789012/runveil-public-test"


async def due(sessions: async_sessionmaker[AsyncSession], run_id: UUID) -> None:
    async with sessions.begin() as session:
        await session.execute(
            text("UPDATE worker_jobs SET admission_not_before=clock_timestamp() WHERE run_id=:id"),
            {"id": run_id},
        )


async def reject_three(sessions: async_sessionmaker[AsyncSession], run_id: UUID) -> None:
    for count in range(1, 4):
        await due(sessions, run_id)
        with pytest.raises(ConfigurationRejected):
            await work_once(sessions, profile=CALLS_PROFILE, run_id=run_id)
        state = await inspect_admission(sessions, run_id)
        assert state.failures == count and state.revision == count
        assert await claim_next(sessions, profile=CALLS_PROFILE, run_id=run_id) is None
        assert await claim_publication(sessions, profile=CALLS_PROFILE, queue_url=URL) is None
    assert state.quarantined_at is not None


async def test_quarantine_suppresses_both_transports_and_verified_release(
    database: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    sessions = async_sessionmaker(database)
    run_id = await submit(sessions, profile=CALLS_PROFILE, queue_url=URL)
    config = configuration(CALLS_PROFILE)
    wrong = config.model_copy(update={"max_steps": 7})
    async with sessions() as session:
        before = await HistoryRepository(session).events(run_id)
    with monkeypatch.context() as patch:
        patch.setattr(worker, "configuration", lambda profile: wrong)
        await reject_three(sessions, run_id)
    async with sessions() as session:
        assert await HistoryRepository(session).events(run_id) == before
        assert await load_runtime_state(session, run_id) is None
        assert await session.scalar(select(func.count()).select_from(ModelInvocationRow)) == 0
    await due(sessions, run_id)
    assert await work_once(sessions, profile=CALLS_PROFILE, run_id=run_id) is None
    assert await claim_publication(sessions, profile=CALLS_PROFILE, queue_url=URL) is None
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
            "receive_message",
            {
                "Messages": [
                    {
                        "Body": Notification(run_id=run_id).model_dump_json(),
                        "ReceiptHandle": "quarantined",
                    }
                ]
            },
            {
                "QueueUrl": URL,
                "MaxNumberOfMessages": 1,
                "WaitTimeSeconds": 10,
                "VisibilityTimeout": 30,
            },
        )
        assert await consume_once(sessions, SqsQueue(sdk, URL)) == "deferred"
        stub.assert_no_pending_responses()
    with pytest.raises(ValueError, match="binding"):
        await release_quarantine(
            sessions, run_id, expected_revision=3, profile=CALLS_PROFILE, expected_config=wrong
        )
    outcomes = await asyncio.gather(
        *(
            release_quarantine(
                sessions, run_id, expected_revision=3, profile=CALLS_PROFILE, expected_config=config
            )
            for _ in range(2)
        ),
        return_exceptions=True,
    )
    assert sum(isinstance(o, RevisionConflict) for o in outcomes) == 1
    status = await inspect_admission(sessions, run_id)
    assert status.failures == 0 and status.revision == 4 and status.quarantined_at is None
    assert await claim_publication(sessions, profile=CALLS_PROFILE, queue_url=URL) is not None
    outcome = await work_once(sessions, profile=CALLS_PROFILE, run_id=run_id)
    assert outcome is not None and outcome[1].final_result is not None
    async with sessions() as session:
        events = list(
            await session.scalars(select(AdmissionEventRow).order_by(AdmissionEventRow.revision))
        )
        assert [(e.action, e.failures) for e in events] == [
            ("rejected", 1),
            ("rejected", 2),
            ("rejected", 3),
            ("released", 0),
        ]


async def test_invalid_pin_cannot_be_repaired_in_place_or_released_after_cancel(
    database: AsyncEngine,
) -> None:
    sessions = async_sessionmaker(database)
    async with sessions.begin() as session:
        agents = AgentRepository(session)
        agent = await agents.create("Invalid public admission fixture")
        version = await agents.create_version(agent.id, {"schema_version": 999})
        run = await RunRepository(session).create(version.id)
        await enroll(session, run.id, task="Public task", profile=CALLS_PROFILE)
    await reject_three(sessions, run.id)
    with pytest.raises(ValueError, match="invalid"):
        await release_quarantine(
            sessions,
            run.id,
            expected_revision=3,
            profile=CALLS_PROFILE,
            expected_config=configuration(CALLS_PROFILE),
        )
    async with sessions.begin() as session:
        await RunRepository(session).transition(run.id, RunStatus.CANCELLED, expected_revision=0)
    with pytest.raises(InvalidTransition):
        await release_quarantine(
            sessions,
            run.id,
            expected_revision=3,
            profile=CALLS_PROFILE,
            expected_config=configuration(CALLS_PROFILE),
        )
    assert (await inspect_admission(sessions, run.id)).failures == 3


async def test_rejection_fences_rollback_and_immutable_audit(
    database: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    sessions = async_sessionmaker(database)
    run_id = await submit(sessions, profile=CALLS_PROFILE)
    old = await claim_next(sessions, profile=CALLS_PROFILE, run_id=run_id)
    assert old is not None
    async with sessions.begin() as session:
        await session.execute(text("UPDATE worker_jobs SET expires_at=clock_timestamp()"))
    current = await claim_next(sessions, profile=CALLS_PROFILE, run_id=run_id)
    assert current is not None
    with pytest.raises(OwnershipLost):
        await record_configuration_rejection(sessions, old)

    def fail_audit(session: AsyncSession, job: JobRow, action: str) -> None:
        raise RuntimeError("simulated rollback")

    with monkeypatch.context() as patch:
        patch.setattr(admission, "audit", fail_audit)
        with pytest.raises(RuntimeError, match="rollback"):
            await record_configuration_rejection(sessions, current)
    assert (await inspect_admission(sessions, run_id)).failures == 0
    await record_configuration_rejection(sessions, current)
    with pytest.raises(OwnershipLost):
        await record_configuration_rejection(sessions, current)
    assert (await inspect_admission(sessions, run_id)).failures == 1
    for statement in (
        "UPDATE worker_admission_events SET action='released',failures=0",
        "DELETE FROM worker_admission_events",
    ):
        with pytest.raises(IntegrityError):
            async with sessions.begin() as session:
                await session.execute(text(statement))
    await due(sessions, run_id)
    claim = await claim_next(sessions, profile=CALLS_PROFILE, run_id=run_id)
    assert claim is not None
    async with sessions.begin() as session:
        await RunRepository(session).transition(run_id, RunStatus.CANCELLED, expected_revision=0)
    with pytest.raises(InvalidTransition):
        await record_configuration_rejection(sessions, claim)
    assert (await inspect_admission(sessions, run_id)).failures == 1


async def test_release_preserves_uncertain_intent_and_original_deadline(
    database: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    sessions = async_sessionmaker(database)
    config = configuration(CALLS_PROFILE)
    run_id = await submit(sessions, profile=CALLS_PROFILE)
    claim = await claim_next(sessions, profile=CALLS_PROFILE, run_id=run_id)
    assert claim is not None

    class Crash(PostgresExecutionStore):
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
            await super().request(
                cursor,
                kind=kind,
                payload=payload,
                config=config,
                model_invocation_id=model_invocation_id,
                tool_name=tool_name,
            )
            raise asyncio.CancelledError

    with pytest.raises(asyncio.CancelledError):
        await execute(
            run_id,
            claim.task,
            provider_name=config.provider,
            provider=TokenFixtureProvider(2),
            tools=fixture_registry(),
            tool_policy=POLICY,
            store=Crash(sessions, claim=claim, expected_config=config),
        )
    async with sessions.begin() as session:
        before = await HistoryRepository(session).events(run_id)
        job = await session.get(JobRow, run_id)
        assert job is not None
        deadline = job.deadline_at
        await session.execute(text("UPDATE worker_jobs SET expires_at=clock_timestamp()"))
    with monkeypatch.context() as patch:
        patch.setattr(
            worker, "configuration", lambda profile: config.model_copy(update={"max_steps": 7})
        )
        await reject_three(sessions, run_id)
    await release_quarantine(
        sessions, run_id, expected_revision=3, profile=CALLS_PROFILE, expected_config=config
    )
    async with sessions() as session:
        assert await HistoryRepository(session).events(run_id) == before
        job = await session.get(JobRow, run_id)
        assert job is not None and job.deadline_at == deadline
    outcome = await work_once(sessions, profile=CALLS_PROFILE, run_id=run_id)
    assert outcome is not None and outcome[1].error_code == "execution_interrupted"
    async with sessions() as session:
        assert await session.scalar(select(func.count()).select_from(ModelInvocationRow)) == 1


async def test_unclassified_start_failure_does_not_count(
    database: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    sessions = async_sessionmaker(database)
    run_id = await submit(sessions, profile=CALLS_PROFILE)

    async def unexpected(
        self: PostgresExecutionStore, run_id: UUID, task: str, provider: str
    ) -> Started:
        raise ValueError("unclassified start failure")

    monkeypatch.setattr(PostgresExecutionStore, "start", unexpected)
    with pytest.raises(ValueError, match="unclassified"):
        await work_once(sessions, profile=CALLS_PROFILE, run_id=run_id)
    assert (await inspect_admission(sessions, run_id)).failures == 0
    assert await claim_next(sessions, profile=CALLS_PROFILE, run_id=run_id) is None
