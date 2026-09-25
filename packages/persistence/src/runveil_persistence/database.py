"""Explicit database configuration; no implicit connections or migrations."""

import os

from sqlalchemy.engine import URL, make_url
from sqlalchemy.exc import ArgumentError
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine


def database_url(value: str | None = None) -> URL:
    raw = value if value is not None else os.environ.get("DATABASE_URL")
    if not raw:
        raise ValueError("DATABASE_URL must be set explicitly")
    try:
        url = make_url(raw)
    except (ArgumentError, ValueError):
        raise ValueError("DATABASE_URL must be a valid PostgreSQL psycopg URL") from None
    if url.drivername != "postgresql+psycopg" or not url.database:
        raise ValueError("DATABASE_URL must use postgresql+psycopg and name a database")
    return url


def create_engine(url: URL) -> AsyncEngine:
    return create_async_engine(
        url, pool_pre_ping=True, hide_parameters=True, connect_args={"connect_timeout": 5}
    )
