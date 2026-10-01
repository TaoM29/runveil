"""Authenticated local inspection, with no execution or approval authority."""

import asyncio
import hmac
from typing import cast
from uuid import UUID

from fastapi import APIRouter, Request, Security
from fastapi.responses import JSONResponse
from fastapi.security import HTTPBearer
from runveil_core.errors import NotFound, RevisionConflict
from runveil_persistence.traces import RunTrace, read_trace
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from runveil_api.approvals import HEADERS, error, token_digest

router = APIRouter(dependencies=[Security(HTTPBearer(auto_error=False))])
REQUEST_TIMEOUT = 5.0
RESPONSE_LIMIT = 512 * 1024


@router.get("/runs/{run_id}/trace", response_model=RunTrace)
async def get_trace(request: Request, run_id: str) -> JSONResponse:
    configured = cast(bytes | None, getattr(request.app.state, "trace_token_digest", None))
    if configured is None:
        return error(503, "traces_disabled")
    headers = request.headers.getlist("authorization")
    provided = (
        token_digest(headers[0][7:])
        if (len(headers) == 1 and headers[0].startswith("Bearer "))
        else None
    )
    if provided is None or not hmac.compare_digest(configured, provided):
        return error(401, "unauthorized")
    try:
        identity = UUID(run_id)
        params = request.query_params
        allowed = {"after_sequence", "limit", "expected_sequence"}
        if any(key not in allowed or len(params.getlist(key)) != 1 for key in params):
            raise ValueError("Invalid query")
        if any(
            not value.isascii() or not value.isdecimal() or len(value) > 10
            for value in params.values()
        ):
            raise ValueError("Invalid integer")
        after = int(params.get("after_sequence", "0"))
        limit = int(params.get("limit", "50"))
        expected = int(params["expected_sequence"]) if "expected_sequence" in params else None
        if (
            not 0 <= after <= 2**31 - 1
            or not 1 <= limit <= 100
            or (expected is not None and not 0 <= expected <= 2**31 - 1)
            or (after and expected is None)
        ):
            raise ValueError("Invalid pagination")
    except ValueError:
        return error(422, "invalid_request")
    engine = cast(AsyncEngine | None, getattr(request.app.state, "database", None))
    if engine is None:
        return error(503, "unavailable")
    try:
        async with asyncio.timeout(REQUEST_TIMEOUT):
            async with async_sessionmaker(engine).begin() as session:
                await session.execute(
                    text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
                )
                trace = await read_trace(
                    session, identity, after_sequence=after, limit=limit, expected_sequence=expected
                )
                response = JSONResponse(trace.model_dump(mode="json"), headers=HEADERS)
                if len(response.body) > RESPONSE_LIMIT:
                    return error(503, "trace_too_large")
            return response
    except NotFound:
        return error(404, "run_not_found")
    except RevisionConflict:
        return error(409, "trace_changed")
    except ValueError:
        return error(409, "trace_unavailable")
    except (SQLAlchemyError, OSError, TimeoutError):
        return error(503, "unavailable")
