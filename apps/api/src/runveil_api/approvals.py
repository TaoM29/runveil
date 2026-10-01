"""Local operator control surface; decisions never dispatch work or grant WRITE."""

import asyncio
import hashlib
import hmac
import re
from typing import Annotated, Final, Literal, cast
from uuid import UUID

from fastapi import APIRouter, Request, Security
from fastapi.responses import JSONResponse
from fastapi.security import HTTPBearer
from pydantic import Field, ValidationError
from runveil_core.approvals import REVIEW_CONFIGURATION, REVIEW_PROFILE, ApprovalRequest
from runveil_core.errors import InvalidTransition, NotFound, RevisionConflict
from runveil_core.models import Contract
from runveil_core.mutations import APPLY_TOOL, PATCH_PROFILE
from runveil_core.runs import RunStatus
from runveil_core.runtime import RuntimeConfig, WorkspaceIdentity
from runveil_persistence.approvals import ApprovalRepository
from runveil_persistence.jobs import OwnershipLost
from runveil_persistence.models import JobRow, RunRow, ToolCallRow
from runveil_persistence.repositories import AgentRepository, RunRepository
from runveil_persistence.worker_approvals import resolve_worker_review
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

# Advertise bearer auth in OpenAPI; handle() performs the fail-closed comparison.
router = APIRouter(dependencies=[Security(HTTPBearer(auto_error=False))])
STANDALONE: Final = "patch-review-v1"
type Profile = Literal["patch-review-v1", "repository-review-v1", "repository-patch-v1"]
REQUEST_LIMIT = 2048
REQUEST_TIMEOUT = 5.0
HEADERS = {"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"}


def token_digest(token: str | None) -> bytes | None:
    """Require a generated URL-safe operator secret; no fallback/default credential."""
    if token is None or re.fullmatch(r"[A-Za-z0-9_-]{43,128}", token) is None:
        return None
    return hashlib.sha256(token.encode("ascii")).digest()


class Decision(Contract):
    decision: Literal["APPROVED", "REJECTED"]
    expected_profile: Profile
    expected_approval_id: UUID
    expected_revision: Annotated[int, Field(ge=0)]
    expected_digest: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]


class Mutation(Contract):
    status: str
    error_code: str | None


class Inspection(Contract):
    request: ApprovalRequest
    profile: Profile
    run_status: RunStatus
    run_revision: int
    workspace: WorkspaceIdentity | None
    mutation: Mutation | None


async def inspect(session: AsyncSession, run_id: UUID) -> Inspection:
    # Same lock order as the resolvers/workers; reads cannot mix revisions and outcomes.
    row = await session.scalar(select(RunRow).where(RunRow.id == run_id).with_for_update())
    if row is None:
        raise NotFound("Run not found")
    run = await RunRepository(session).get(run_id)
    version = await AgentRepository(session).get_version(run.agent_version_id)
    job = await session.get(JobRow, run_id)
    workspace = None
    profile: Profile
    if job is None and version.configuration == REVIEW_CONFIGURATION:
        profile = STANDALONE
    else:
        config = RuntimeConfig.model_validate_json(version.configuration_json)
        if (
            job is None
            or config.schema_version not in (10, 11)
            or job.profile != (PATCH_PROFILE if config.schema_version == 11 else REVIEW_PROFILE)
        ):
            raise ValueError("Unsupported approval profile")
        profile = cast(Profile, job.profile)
        workspace = config.workspace
    approval = await ApprovalRepository(session).get(run_id)
    call = await session.scalar(
        select(ToolCallRow).where(ToolCallRow.run_id == run_id, ToolCallRow.tool_name == APPLY_TOOL)
    )
    return Inspection(
        request=approval,
        profile=profile,
        run_status=run.status,
        run_revision=run.revision,
        workspace=workspace,
        mutation=Mutation(status=call.status, error_code=call.error_code) if call else None,
    )


def error(status: int, code: str) -> JSONResponse:
    return JSONResponse({"error": code}, status_code=status, headers=HEADERS)


async def handle(request: Request, run_id: str, *, deciding: bool) -> JSONResponse:
    configured = cast(bytes | None, getattr(request.app.state, "approval_token_digest", None))
    if configured is None:
        return error(503, "approvals_disabled")
    headers = request.headers.getlist("authorization")
    provided = (
        token_digest(headers[0][7:])
        if len(headers) == 1 and headers[0].startswith("Bearer ")
        else None
    )
    if provided is None or not hmac.compare_digest(configured, provided):
        return error(401, "unauthorized")
    try:
        identity = UUID(run_id)
    except ValueError:
        return error(422, "invalid_request")
    engine = cast(AsyncEngine | None, getattr(request.app.state, "database", None))
    if engine is None:
        return error(503, "unavailable")
    try:
        async with asyncio.timeout(REQUEST_TIMEOUT):
            decision = None
            if deciding:
                if (
                    request.headers.get("content-type", "").split(";")[0].strip()
                    != "application/json"
                ):
                    return error(415, "json_required")
                body = bytearray()
                async for chunk in request.stream():
                    if len(body) + len(chunk) > REQUEST_LIMIT:
                        return error(413, "request_too_large")
                    body.extend(chunk)
                try:
                    decision = Decision.model_validate_json(bytes(body))
                except ValidationError:
                    return error(422, "invalid_request")
            async with async_sessionmaker(engine).begin() as session:
                result = await inspect(session, identity)
                if decision is not None:
                    if (
                        result.profile != decision.expected_profile
                        or result.request.id != decision.expected_approval_id
                    ):
                        raise RevisionConflict("Inspection binding changed")
                    if result.profile == STANDALONE:
                        await ApprovalRepository(session).resolve(
                            identity,
                            decision=decision.decision,
                            expected_revision=decision.expected_revision,
                            expected_digest=decision.expected_digest,
                        )
                    else:
                        await resolve_worker_review(
                            session,
                            identity,
                            decision=decision.decision,
                            expected_revision=decision.expected_revision,
                            expected_digest=decision.expected_digest,
                            profile=result.profile,
                        )
                    result = await inspect(session, identity)
            # Only acknowledge after transaction commit. A lost response requires inspection.
            return JSONResponse(result.model_dump(mode="json"), headers=HEADERS)
    except NotFound:
        return error(404, "approval_not_found")
    except (RevisionConflict, InvalidTransition, OwnershipLost, ValueError):
        return error(409, "inspection_required")
    except (SQLAlchemyError, OSError, TimeoutError):
        return error(503, "unavailable")


@router.get("/approvals/{run_id}", response_model=Inspection)
async def get_approval(request: Request, run_id: str) -> JSONResponse:
    return await handle(request, run_id, deciding=False)


@router.post(
    "/approvals/{run_id}/decision",
    response_model=Inspection,
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {"application/json": {"schema": Decision.model_json_schema()}},
        },
    },
)
async def decide_approval(request: Request, run_id: str) -> JSONResponse:
    return await handle(request, run_id, deciding=True)
