"""Exercise actual PostgreSQL runtime grants through the fixed-fixture queue path."""

from contextlib import closing

import boto3
import pytest
from botocore.stub import Stubber
from runveil_persistence.database import create_engine
from runveil_persistence.deployment import ROLES, migrate, require_schema
from runveil_persistence.traces import read_trace
from runveil_worker.sqs import Notification, SqsQueue, consume_once, publish_once
from runveil_worker.worker import CALLS_PROFILE, submit
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def test_private_roles_migrate_execute_and_refuse_crossed_authority(
    empty_database: AsyncEngine,
) -> None:
    passwords = {"api": "1" * 64, "worker": "2" * 64, "relay": "3" * 64}
    owned: list[str] = []
    engines: dict[str, AsyncEngine] = {}
    try:
        # Never modify existing cluster roles, including roles belonging to a developer.
        async with empty_database.begin() as connection:
            if await connection.scalar(
                text(
                    "SELECT 1 FROM pg_roles WHERE rolname IN "
                    "('runveil_api','runveil_worker','runveil_relay','runveil_test_migrator')"
                )
            ):
                pytest.skip("Deployment acceptance requires unused runtime role names")
            await connection.execute(
                text(
                    "CREATE ROLE runveil_test_migrator LOGIN CREATEROLE NOINHERIT PASSWORD '"
                    + "4" * 64
                    + "'"
                )
            )
            database_name = connection.dialect.identifier_preparer.quote(
                str(empty_database.url.database)
            )
            await connection.execute(
                text(f"ALTER DATABASE {database_name} OWNER TO runveil_test_migrator")
            )
        owned.append("runveil_test_migrator")
        engines["migration"] = create_engine(
            empty_database.url.set(username="runveil_test_migrator", password="4" * 64)
        )
        async with engines["migration"].begin() as connection:
            await connection.run_sync(lambda conn: migrate(conn, passwords))
        owned.extend(ROLES.values())
        # RDS administrators are not PostgreSQL superusers; repeat as the non-superuser owner.
        async with engines["migration"].begin() as connection:
            await connection.run_sync(lambda conn: migrate(conn, passwords))
        for actor, role in ROLES.items():
            engines[actor] = create_engine(
                empty_database.url.set(username=role, password=passwords[actor])
            )
            await require_schema(engines[actor])
        sessions = {actor: async_sessionmaker(engine) for actor, engine in engines.items()}
        url = "https://sqs.eu-west-1.amazonaws.com/123456789012/runveil-test"
        run_id = await submit(
            async_sessionmaker(engines["migration"]), profile=CALLS_PROFILE, queue_url=url
        )
        with (
            closing(
                boto3.client(
                    "sqs",
                    region_name="eu-west-1",
                    aws_access_key_id="offline",
                    aws_secret_access_key="offline",
                )
            ) as sdk,
            Stubber(sdk) as stub,
        ):
            queue = SqsQueue(sdk, url)
            payload = Notification(run_id=run_id).model_dump_json()
            stub.add_response(
                "send_message", {"MessageId": "test"}, {"QueueUrl": url, "MessageBody": payload}
            )
            assert await publish_once(sessions["relay"], queue)
            for _ in range(2):
                stub.add_response(
                    "receive_message",
                    {"Messages": [{"Body": payload, "ReceiptHandle": "test"}]},
                    {
                        "QueueUrl": url,
                        "MaxNumberOfMessages": 1,
                        "WaitTimeSeconds": 10,
                        "VisibilityTimeout": 30,
                    },
                )
                stub.add_response("delete_message", {}, {"QueueUrl": url, "ReceiptHandle": "test"})
                assert await consume_once(sessions["worker"], queue) == "acknowledged"
            stub.assert_no_pending_responses()
        async with sessions["api"].begin() as session:
            trace = await read_trace(session, run_id)
            assert trace.status.value == "SUCCEEDED"
            assert trace.model_calls == 2 and trace.tool_calls == 1
        for actor, statement in (
            ("api", "UPDATE runs SET revision=revision WHERE false"),
            ("api", "SELECT * FROM worker_outbox"),
            ("worker", "CREATE TABLE forbidden (id integer)"),
            ("worker", "UPDATE worker_outbox SET token=NULL WHERE false"),
            ("worker", "DELETE FROM execution_events WHERE false"),
            ("worker", "ALTER TABLE runs DISABLE TRIGGER ALL"),
            ("relay", "UPDATE runs SET revision=revision WHERE false"),
            ("relay", "SELECT * FROM checkpoints"),
        ):
            with pytest.raises(DBAPIError):
                async with engines[actor].begin() as connection:
                    await connection.execute(text(statement))
        async with empty_database.begin() as connection:
            await connection.execute(text("UPDATE alembic_version SET version_num='0009'"))
        with pytest.raises(ValueError, match="schema mismatch"):
            await require_schema(engines["api"])
    finally:
        for engine in engines.values():
            await engine.dispose()
        async with empty_database.begin() as connection:
            if owned:
                quote = connection.dialect.identifier_preparer.quote
                await connection.execute(
                    text(
                        f"ALTER DATABASE {quote(str(empty_database.url.database))} "
                        f"OWNER TO {quote(str(empty_database.url.username))}"
                    )
                )
            for role in reversed(owned):
                await connection.execute(text(f"DROP OWNED BY {role}"))
                await connection.execute(text(f"DROP ROLE {role}"))
