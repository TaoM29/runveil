"""Liveness and bounded database connectivity readiness."""

import asyncio
from typing import Literal

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncEngine

router = APIRouter()


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
    service: Literal["api"] = "api"


@router.get("/health", response_model=HealthResponse, tags=["health"])
async def health() -> HealthResponse:
    return HealthResponse()


@router.get("/ready", tags=["health"], responses={503: {"description": "Database unavailable"}})
async def ready(request: Request) -> JSONResponse:
    engine: AsyncEngine | None = getattr(request.app.state, "database", None)
    if engine is not None:
        try:
            async with asyncio.timeout(2):
                async with engine.connect() as connection:
                    await connection.execute(text("SELECT 1"))
            return JSONResponse(
                {"status": "ok", "database": "reachable"}, headers={"Cache-Control": "no-store"}
            )
        except (SQLAlchemyError, OSError, TimeoutError):
            # Translate only at the HTTP boundary; never expose driver errors or credentials.
            pass
    return JSONResponse(
        {"status": "unavailable", "database": "unavailable"},
        status_code=503,
        headers={"Cache-Control": "no-store"},
    )
