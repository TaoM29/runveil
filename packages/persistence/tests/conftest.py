"""Each integration test gets a new migrated database; never reset a user's DB."""

import os
from collections.abc import AsyncIterator
from pathlib import Path
from uuid import uuid4

import pytest
import pytest_asyncio
from alembic import command
from alembic.config import Config
from runveil_persistence.database import create_engine, database_url
from sqlalchemy import Connection, text
from sqlalchemy.ext.asyncio import AsyncEngine

ROOT = Path(__file__).resolve().parents[3]


def migration_config(connection: Connection) -> Config:
    config = Config(str(ROOT / "alembic.ini"))
    config.attributes["connection"] = connection
    return config


@pytest_asyncio.fixture
async def empty_database() -> AsyncIterator[AsyncEngine]:
    raw = os.environ.get("RUNVEIL_TEST_DATABASE_URL")
    if not raw:
        pytest.skip("Set RUNVEIL_TEST_DATABASE_URL to run real PostgreSQL integration tests")
    admin_url = database_url(raw)
    admin = create_engine(admin_url).execution_options(isolation_level="AUTOCOMMIT")
    name = f"runveil_test_{uuid4().hex}"
    engine = create_engine(admin_url.set(database=name))
    created = False
    try:
        async with admin.connect() as connection:
            await connection.execute(text(f'CREATE DATABASE "{name}"'))
        created = True
        yield engine
    finally:
        await engine.dispose()
        if created:
            async with admin.connect() as connection:
                await connection.execute(text(f'DROP DATABASE "{name}" WITH (FORCE)'))
        await admin.dispose()


@pytest_asyncio.fixture
async def database(empty_database: AsyncEngine) -> AsyncEngine:
    async with empty_database.begin() as connection:
        await connection.run_sync(lambda conn: command.upgrade(migration_config(conn), "head"))
    return empty_database
