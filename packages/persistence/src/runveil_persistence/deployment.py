"""Explicit private-deployment configuration, schema gate and database grants."""

import os
import re
from collections.abc import Mapping

from alembic import command
from alembic.config import Config
from sqlalchemy import Connection, text
from sqlalchemy.engine import URL
from sqlalchemy.ext.asyncio import AsyncEngine

SCHEMA_REVISION = "0010"
ROLES = {"api": "runveil_api", "worker": "runveil_worker", "relay": "runveil_relay"}
TABLES = (
    "agent_versions, runs, run_steps, execution_events, checkpoints, "
    "model_invocations, tool_calls, worker_jobs, worker_outbox, worker_admission_events"
)


def cloud_database_url(environ: Mapping[str, str] = os.environ) -> URL:
    host = environ["RUNVEIL_DB_HOST"]
    user = environ["RUNVEIL_DB_USER"]
    password = environ["RUNVEIL_DB_PASSWORD"]
    if not host or not user or not password:
        raise ValueError("Missing deployment database configuration")
    return URL.create(
        "postgresql+psycopg",
        username=user,
        password=password,
        host=host,
        port=5432,
        database="runveil",
        query={"sslmode": "verify-full", "sslrootcert": "/app/certs/rds.pem"},
    )


async def require_schema(engine: AsyncEngine) -> None:
    async with engine.connect() as connection:
        revisions = (
            await connection.execute(text("SELECT version_num FROM alembic_version"))
        ).scalars()
        if list(revisions) != [SCHEMA_REVISION]:
            raise ValueError("Deployment schema mismatch")


def migrate(connection: Connection, passwords: Mapping[str, str]) -> None:
    """The caller owns one transaction and the privileged migration connection."""
    if set(passwords) != set(ROLES) or any(
        re.fullmatch(r"[a-f0-9]{64}", value) is None for value in passwords.values()
    ):
        raise ValueError("Runtime passwords must be independent 32-byte hex secrets")
    if len(set(passwords.values())) != len(ROLES):
        raise ValueError("Runtime passwords must be distinct")
    if not connection.scalar(text("SELECT pg_try_advisory_xact_lock(120012)")):
        raise ValueError("Another migration is running")
    config = Config("/app/alembic.ini" if os.path.isfile("/app/alembic.ini") else "alembic.ini")
    config.attributes["connection"] = connection
    command.upgrade(config, SCHEMA_REVISION)
    command.check(config)
    database = connection.scalar(text("SELECT current_database()"))
    assert isinstance(database, str)
    quoted_database = connection.dialect.identifier_preparer.quote(database)
    connection.execute(text(f"REVOKE ALL ON DATABASE {quoted_database} FROM PUBLIC"))
    connection.execute(text("REVOKE ALL ON SCHEMA public FROM PUBLIC"))
    connection.execute(text("REVOKE ALL ON ALL TABLES IN SCHEMA public FROM PUBLIC"))
    for actor, role in ROLES.items():
        exists = connection.scalar(
            text("SELECT 1 FROM pg_roles WHERE rolname=:role"), {"role": role}
        )
        if not exists:
            connection.execute(text(f"CREATE ROLE {role} LOGIN"))
        if connection.scalar(
            text(
                "SELECT 1 FROM pg_shdepend d JOIN pg_roles r ON r.oid=d.refobjid "
                "WHERE d.refclassid='pg_authid'::regclass AND d.deptype='o' "
                "AND r.rolname=:role LIMIT 1"
            ),
            {"role": role},
        ):
            raise ValueError("Runtime role owns database objects")
        if connection.scalar(
            text(
                "SELECT 1 FROM pg_roles WHERE rolname=:role "
                "AND (rolsuper OR rolreplication OR rolbypassrls OR rolcreatedb OR rolcreaterole)"
            ),
            {"role": role},
        ):
            raise ValueError("Runtime role has elevated attributes")
        # Identifiers are constants; password interpolation is restricted to exactly 64 hex digits.
        connection.execute(
            text(f"ALTER ROLE {role} WITH LOGIN NOINHERIT PASSWORD '{passwords[actor]}'")
        )
        if connection.scalar(
            text(
                "SELECT 1 FROM pg_auth_members m JOIN pg_roles r ON r.oid=m.member "
                "WHERE r.rolname=:role LIMIT 1"
            ),
            {"role": role},
        ):
            raise ValueError("Runtime role has unexpected memberships")
        connection.execute(text(f"REVOKE ALL ON ALL TABLES IN SCHEMA public FROM {role}"))
        connection.execute(text(f"REVOKE ALL ON SCHEMA public FROM {role}"))
        connection.execute(text(f"REVOKE ALL ON DATABASE {quoted_database} FROM {role}"))
        connection.execute(text(f"GRANT CONNECT ON DATABASE {quoted_database} TO {role}"))
        connection.execute(text(f"GRANT USAGE ON SCHEMA public TO {role}"))
        connection.execute(text(f"GRANT SELECT ON alembic_version TO {role}"))
        connection.execute(text(f"ALTER ROLE {role} SET search_path = public, pg_catalog"))
        connection.execute(text(f"ALTER ROLE {role} SET statement_timeout = '15s'"))
        connection.execute(text(f"ALTER ROLE {role} SET lock_timeout = '5s'"))
        connection.execute(
            text(f"ALTER ROLE {role} SET idle_in_transaction_session_timeout = '30s'")
        )
    connection.execute(
        text(
            "GRANT SELECT ON runs, execution_events, checkpoints, model_invocations, "
            "tool_calls, approval_requests TO runveil_api"
        )
    )
    connection.execute(text(f"GRANT SELECT ON {TABLES} TO runveil_worker"))
    connection.execute(
        text("GRANT UPDATE ON runs, worker_jobs, model_invocations, tool_calls TO runveil_worker")
    )
    connection.execute(
        text(
            "GRANT INSERT ON run_steps, execution_events, checkpoints, model_invocations, "
            "tool_calls, worker_admission_events TO runveil_worker"
        )
    )
    connection.execute(text("GRANT SELECT ON runs, worker_jobs, worker_outbox TO runveil_relay"))
    connection.execute(
        text("GRANT UPDATE (next_publish_at, token, expires_at) ON worker_outbox TO runveil_relay")
    )
