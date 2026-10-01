"""Opt-in, one-shot SQS notification relay/consumer for the public calls fixture."""

import argparse
import asyncio
import re
from contextlib import closing
from typing import TYPE_CHECKING, Literal
from uuid import UUID

import boto3
from botocore.config import Config
from pydantic import ValidationError
from runveil_core.models import Contract
from runveil_persistence.database import create_engine, database_url
from runveil_persistence.outbox import TERMINAL, claim_publication, delivery_status, published
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from runveil_worker.telemetry import telemetry
from runveil_worker.worker import CALLS_PROFILE, submit, work_once

if TYPE_CHECKING:
    from mypy_boto3_sqs import SQSClient


class Notification(Contract):
    schema_version: Literal[1] = 1
    run_id: UUID


def queue_region(queue_url: str) -> str:
    match = re.fullmatch(
        r"https://sqs\.([a-z]{2}-[a-z]+-\d+)\.amazonaws\.com/\d{12}/[A-Za-z0-9_-]{1,80}",
        queue_url,
    )
    if match is None:
        raise ValueError("Expected a commercial regional SQS Standard queue URL")
    return match[1]


class SqsQueue:
    def __init__(self, client: "SQSClient", queue_url: str) -> None:
        queue_region(queue_url)
        self.client = client
        self.url = queue_url

    async def send(self, notification: Notification) -> None:
        await asyncio.to_thread(
            self.client.send_message, QueueUrl=self.url, MessageBody=notification.model_dump_json()
        )

    async def receive(self) -> tuple[Notification, str] | Literal["rejected"] | None:
        response = await asyncio.to_thread(
            self.client.receive_message,
            QueueUrl=self.url,
            MaxNumberOfMessages=1,
            WaitTimeSeconds=10,
            VisibilityTimeout=30,
        )
        messages = response.get("Messages", [])
        if not messages:
            return None
        body = messages[0].get("Body", "")
        receipt = messages[0].get("ReceiptHandle", "")
        if not 1 <= len(body.encode("utf-8")) <= 1024 or not 1 <= len(receipt) <= 2048:
            return "rejected"
        try:
            return Notification.model_validate_json(body), receipt
        except ValidationError:
            return "rejected"

    async def delete(self, receipt: str) -> None:
        await asyncio.to_thread(
            self.client.delete_message, QueueUrl=self.url, ReceiptHandle=receipt
        )


async def publish_once(sessions: async_sessionmaker[AsyncSession], queue: SqsQueue) -> bool:
    claim = await claim_publication(sessions, queue_url=queue.url, profile=CALLS_PROFILE)
    if claim is None:
        return False
    # No transaction spans network I/O. Failed/uncertain sends leave the lease to expire.
    await queue.send(Notification(run_id=claim.run_id))
    await published(sessions, claim)
    return True


async def consume_once(sessions: async_sessionmaker[AsyncSession], queue: SqsQueue) -> str:
    received = await queue.receive()
    if received is None:
        return "no_message"
    if received == "rejected":
        return "rejected"
    notification, receipt = received
    status = await delivery_status(
        sessions, run_id=notification.run_id, queue_url=queue.url, profile=CALLS_PROFILE
    )
    if status is None:
        return "rejected"
    if status not in TERMINAL:
        await work_once(sessions, run_id=notification.run_id, profile=CALLS_PROFILE)
        status = await delivery_status(
            sessions, run_id=notification.run_id, queue_url=queue.url, profile=CALLS_PROFILE
        )
    if status in TERMINAL:
        await queue.delete(receipt)
        return "acknowledged"
    return "deferred"


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("submit", "publish", "work"))
    parser.add_argument("--queue-url", required=True)
    args = parser.parse_args()
    try:
        region = queue_region(args.queue_url)
    except ValueError:
        parser.error("Expected a commercial regional SQS Standard queue URL")
    engine = create_engine(database_url())
    try:
        sessions = async_sessionmaker(engine)
        if args.command == "submit":
            run_id = await submit(sessions, profile=CALLS_PROFILE, queue_url=args.queue_url)
            print(f"run_id={run_id}")
            return 0
        with closing(
            boto3.client(
                "sqs",
                region_name=region,
                endpoint_url=f"https://sqs.{region}.amazonaws.com",
                config=Config(
                    connect_timeout=3,
                    read_timeout=25,
                    retries={"total_max_attempts": 1, "mode": "standard"},
                ),
            )
        ) as client:
            queue = SqsQueue(client, args.queue_url)
            if args.command == "publish":
                print("published" if await publish_once(sessions, queue) else "no_eligible_work")
                return 0
            outcome = await consume_once(sessions, queue)
            print(outcome)
            return 1 if outcome == "rejected" else 0
    finally:
        await engine.dispose()


def entrypoint() -> int:
    try:
        with telemetry():
            return asyncio.run(main())
    except (KeyboardInterrupt, asyncio.CancelledError):
        return 130
    except Exception:
        print("broker_failed")
        return 1


if __name__ == "__main__":
    raise SystemExit(entrypoint())
