"""Bounded supervision of the existing one-shot fixed-fixture SQS adapters."""

import asyncio
import signal
from collections.abc import Awaitable, Callable
from contextlib import closing
from typing import Literal

import boto3
from botocore.config import Config
from runveil_persistence.database import create_engine
from runveil_persistence.deployment import cloud_database_url, require_schema
from sqlalchemy.ext.asyncio import async_sessionmaker

from runveil_worker.sqs import SqsQueue, consume_once, publish_once, queue_region


async def supervise(operation: Callable[[], Awaitable[object]], stop: asyncio.Event) -> None:
    failures = 0
    while not stop.is_set():
        try:
            await operation()
            failures = 0
            delay = 1.0
        except Exception:
            failures = min(failures + 1, 6)
            delay = float(min(2**failures, 30))
            print("broker_iteration_failed", flush=True)
        try:
            await asyncio.wait_for(stop.wait(), timeout=delay)
        except TimeoutError:
            pass


async def serve(actor: Literal["relay", "worker"], queue_url: str) -> None:
    region = queue_region(queue_url)
    engine = create_engine(cloud_database_url())
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    running = asyncio.current_task()
    assert running is not None
    shutdown: asyncio.TimerHandle | None = None

    def request_stop() -> None:
        nonlocal shutdown
        stop.set()
        if shutdown is None:
            # Leave time for a bounded SDK thread to finish before Fargate's 120s SIGKILL.
            shutdown = loop.call_later(80, running.cancel)

    loop.add_signal_handler(signal.SIGTERM, request_stop)
    loop.add_signal_handler(signal.SIGINT, request_stop)
    try:
        await require_schema(engine)
        sessions = async_sessionmaker(engine)
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
            queue = SqsQueue(client, queue_url)
            print("broker_service_started", flush=True)
            if actor == "relay":
                await supervise(lambda: publish_once(sessions, queue), stop)
            else:
                await supervise(lambda: consume_once(sessions, queue), stop)
    finally:
        if shutdown is not None:
            shutdown.cancel()
        loop.remove_signal_handler(signal.SIGTERM)
        loop.remove_signal_handler(signal.SIGINT)
        await engine.dispose()
