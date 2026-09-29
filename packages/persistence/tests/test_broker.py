"""Offline SQS wire contracts paired with real PostgreSQL consistency boundaries."""

import asyncio
from contextlib import closing
from uuid import UUID, uuid4

import boto3
import pytest
from alembic import command
from botocore.exceptions import ClientError
from botocore.stub import Stubber
from conftest import migration_config
from mypy_boto3_sqs import SQSClient
from runveil_persistence.jobs import OwnershipLost, claim_next
from runveil_persistence.models import ModelInvocationRow, OutboxRow, RunRow, ToolCallRow
from runveil_persistence.outbox import (
    Publication,
    claim_publication,
    enroll_notification,
    published,
)
from runveil_worker import worker
from runveil_worker.sqs import Notification, SqsQueue, consume_once, publish_once, queue_region
from runveil_worker.worker import CALLS_PROFILE, submit, work_once
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]
URL = "https://sqs.us-east-1.amazonaws.com/123456789012/runveil-public-test"
RECEIVE = {
    "QueueUrl": URL,
    "MaxNumberOfMessages": 1,
    "WaitTimeSeconds": 10,
    "VisibilityTimeout": 30,
}


def client() -> SQSClient:
    return boto3.client(
        "sqs", region_name="us-east-1", aws_access_key_id="offline", aws_secret_access_key="offline"
    )


async def test_outbox_migration_atomic_enrollment_and_destination(
    empty_database: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    async with empty_database.begin() as connection:
        await connection.run_sync(lambda c: command.upgrade(migration_config(c), "0006"))
    sessions = async_sessionmaker(empty_database)
    legacy = await submit(sessions)
    async with empty_database.begin() as connection:
        await connection.run_sync(lambda c: command.upgrade(migration_config(c), "head"))
    async with sessions() as session:
        assert await session.get(OutboxRow, legacy) is None
    run_id = await submit(sessions, profile=CALLS_PROFILE, queue_url=URL)
    async with sessions.begin() as session:
        await enroll_notification(session, run_id, URL)
        with pytest.raises(ValueError, match="destination"):
            await enroll_notification(session, run_id, URL + "-other")
    with pytest.raises(IntegrityError):
        async with sessions.begin() as session:
            await session.execute(
                text("UPDATE worker_outbox SET queue_url=:url WHERE run_id=:id"),
                {"url": URL + "-other", "id": run_id},
            )

    async def fail(session: AsyncSession, run_id: UUID, queue_url: str) -> None:
        await enroll_notification(session, run_id, queue_url)
        raise RuntimeError("simulated rollback")

    monkeypatch.setattr(worker, "enroll_notification", fail)
    with pytest.raises(RuntimeError, match="rollback"):
        await submit(sessions, profile=CALLS_PROFILE, queue_url=URL)
    async with sessions() as session:
        assert await session.scalar(select(func.count()).select_from(RunRow)) == 2
        assert await session.scalar(select(func.count()).select_from(OutboxRow)) == 1
    async with empty_database.begin() as connection:
        await connection.run_sync(lambda c: command.downgrade(migration_config(c), "0006"))
        await connection.run_sync(lambda c: command.upgrade(migration_config(c), "head"))
    async with sessions() as session:
        assert await session.scalar(select(func.count()).select_from(RunRow)) == 2
        assert await session.scalar(select(func.count()).select_from(OutboxRow)) == 0


async def test_relay_uncertain_send_fencing_and_rediscovery(database: AsyncEngine) -> None:
    sessions = async_sessionmaker(database)
    run_id = await submit(sessions, profile=CALLS_PROFILE, queue_url=URL)
    payload = {"QueueUrl": URL, "MessageBody": Notification(run_id=run_id).model_dump_json()}
    with closing(client()) as sdk, Stubber(sdk) as stub:
        queue = SqsQueue(sdk, URL)
        stub.add_client_error(
            "send_message", service_error_code="RequestTimeout", expected_params=payload
        )
        with pytest.raises(ClientError):
            await publish_once(sessions, queue)
        async with sessions() as session:
            row = await session.get(OutboxRow, run_id)
            assert row is not None and row.token is not None
            old = Publication(run_id, row.token)
        assert await claim_publication(sessions, queue_url=URL, profile=CALLS_PROFILE) is None
        async with sessions.begin() as session:
            await session.execute(text("UPDATE worker_outbox SET expires_at=clock_timestamp()"))
        claims = await asyncio.gather(
            *(claim_publication(sessions, queue_url=URL, profile=CALLS_PROFILE) for _ in range(2))
        )
        assert sum(c is not None for c in claims) == 1
        current = next(c for c in claims if c is not None)
        with pytest.raises(OwnershipLost):
            await published(sessions, old)
        stub.add_response("send_message", {"MessageId": "published"}, payload)
        await queue.send(Notification(run_id=run_id))
        # Simulate death after AWS accepted a send but before publication completion.
        async with sessions.begin() as session:
            await session.execute(text("UPDATE worker_outbox SET expires_at=clock_timestamp()"))
        with pytest.raises(OwnershipLost):
            await published(sessions, current)
        stub.add_response("send_message", {"MessageId": "duplicate"}, payload)
        assert await publish_once(sessions, queue)
        assert not await publish_once(sessions, queue)
        async with sessions.begin() as session:
            await session.execute(
                text("UPDATE worker_outbox SET next_publish_at=clock_timestamp()")
            )
        claim = await claim_next(sessions, profile=CALLS_PROFILE, run_id=run_id)
        assert claim is not None
        assert not await publish_once(sessions, queue)
        async with sessions.begin() as session:
            await session.execute(text("UPDATE worker_jobs SET expires_at=clock_timestamp()"))
        stub.add_response("send_message", {"MessageId": "recovery"}, payload)
        assert await publish_once(sessions, queue)
        assert await work_once(sessions, profile=CALLS_PROFILE, run_id=run_id) is not None
        async with sessions.begin() as session:
            await session.execute(
                text("UPDATE worker_outbox SET next_publish_at=clock_timestamp()")
            )
        assert not await publish_once(sessions, queue)
        stub.assert_no_pending_responses()


async def test_terminal_commit_before_ack_and_duplicate_delivery(database: AsyncEngine) -> None:
    sessions = async_sessionmaker(database)
    run_id = await submit(sessions, profile=CALLS_PROFILE, queue_url=URL)
    body = Notification(run_id=run_id).model_dump_json()
    with closing(client()) as sdk, Stubber(sdk) as stub:
        queue = SqsQueue(sdk, URL)
        stub.add_response(
            "receive_message", {"Messages": [{"Body": body, "ReceiptHandle": "first"}]}, RECEIVE
        )
        stub.add_client_error(
            "delete_message",
            service_error_code="RequestTimeout",
            expected_params={"QueueUrl": URL, "ReceiptHandle": "first"},
        )
        with pytest.raises(ClientError):
            await consume_once(sessions, queue)
        async with sessions() as session:
            run = await session.get(RunRow, run_id)
            assert run is not None and run.status == "SUCCEEDED"
        stub.add_response(
            "receive_message",
            {"Messages": [{"Body": body, "ReceiptHandle": "redelivery"}]},
            RECEIVE,
        )
        stub.add_response("delete_message", {}, {"QueueUrl": URL, "ReceiptHandle": "redelivery"})
        assert await consume_once(sessions, queue) == "acknowledged"
        async with sessions() as session:
            assert await session.scalar(select(func.count()).select_from(ModelInvocationRow)) == 2
            assert await session.scalar(select(func.count()).select_from(ToolCallRow)) == 1
        stub.assert_no_pending_responses()


async def test_untrusted_or_busy_deliveries_never_acknowledge(database: AsyncEngine) -> None:
    sessions = async_sessionmaker(database)
    run_id = await submit(sessions, profile=CALLS_PROFILE, queue_url=URL)
    other = await submit(sessions, profile=CALLS_PROFILE, queue_url=URL + "-other")
    unenrolled = await submit(sessions, profile=CALLS_PROFILE)
    async with sessions.begin() as session:
        await session.execute(
            text(
                "UPDATE worker_jobs SET available_at=clock_timestamp() + interval '1 hour' "
                "WHERE run_id=:id"
            ),
            {"id": run_id},
        )
    with closing(client()) as sdk, Stubber(sdk) as stub:
        queue = SqsQueue(sdk, URL)
        assert not await publish_once(sessions, queue)
        stub.add_response(
            "receive_message",
            {
                "Messages": [
                    {
                        "Body": Notification(run_id=run_id).model_dump_json(),
                        "ReceiptHandle": "early",
                    }
                ]
            },
            RECEIVE,
        )
        assert await consume_once(sessions, queue) == "deferred"
        stub.assert_no_pending_responses()
    async with sessions.begin() as session:
        await session.execute(
            text("UPDATE worker_jobs SET available_at=clock_timestamp() WHERE run_id=:id"),
            {"id": run_id},
        )
    assert await claim_next(sessions, profile=CALLS_PROFILE, run_id=run_id) is not None
    with closing(client()) as sdk, Stubber(sdk) as stub:
        queue = SqsQueue(sdk, URL)
        for body in (
            "not-json",
            "x" * 1025,
            '{"schema_version":2,"run_id":"' + str(run_id) + '"}',
            Notification(run_id=uuid4()).model_dump_json(),
            Notification(run_id=other).model_dump_json(),
            Notification(run_id=unenrolled).model_dump_json(),
        ):
            stub.add_response(
                "receive_message",
                {"Messages": [{"Body": body, "ReceiptHandle": "untrusted"}]},
                RECEIVE,
            )
            assert await consume_once(sessions, queue) == "rejected"
        stub.add_response(
            "receive_message",
            {
                "Messages": [
                    {"Body": Notification(run_id=run_id).model_dump_json(), "ReceiptHandle": "busy"}
                ]
            },
            RECEIVE,
        )
        assert await consume_once(sessions, queue) == "deferred"
        stub.add_response("receive_message", {}, RECEIVE)
        assert await consume_once(sessions, queue) == "no_message"
        stub.assert_no_pending_responses()
    async with sessions() as session:
        assert await session.scalar(select(func.count()).select_from(ModelInvocationRow)) == 0
    for url in (
        "http://localhost/queue",
        URL + ".fifo",
        URL + "?secret=bad",
        URL.replace("sqs.us-east-1.amazonaws.com", "example.com"),
    ):
        with pytest.raises(ValueError):
            queue_region(url)
