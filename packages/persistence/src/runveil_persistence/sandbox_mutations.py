"""Exact approved sandbox mutation provenance; no Docker I/O in transactions."""

import json
from uuid import UUID

from runveil_core.approvals import PROPOSAL_TOOL
from runveil_core.runtime import RuntimeConfig, RuntimeState
from runveil_core.sandbox_patch import (
    SANDBOX_PATCH_PROFILE,
    SandboxPatchInput,
    authorize_sandbox_patch,
)
from runveil_core.software import SEARCH_PROFILE, SOFTWARE_PROFILE
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from runveil_persistence.approvals import snapshot
from runveil_persistence.history import HistoryRepository
from runveil_persistence.models import JobRow, ToolCallRow
from runveil_persistence.repositories import AgentRepository, RunRepository
from runveil_persistence.worker_approvals import sandbox_preimage, validate_review_state


async def authorized_sandbox_patch(
    session: AsyncSession, run_id: UUID
) -> tuple[RuntimeConfig, SandboxPatchInput]:
    run = await RunRepository(session).get(run_id)
    version = await AgentRepository(session).get_version(run.agent_version_id)
    config = RuntimeConfig.model_validate_json(version.configuration_json)
    job = await session.get(JobRow, run_id)
    checkpoint = await HistoryRepository(session).latest_checkpoint(run_id)
    if (
        config.schema_version not in (14, 15, 16)
        or job is None
        or job.profile
        != {14: SANDBOX_PATCH_PROFILE, 15: SOFTWARE_PROFILE, 16: SEARCH_PROFILE}[
            config.schema_version
        ]
        or checkpoint is None
    ):
        raise ValueError("Sandbox mutation requires its dedicated profile")
    state = RuntimeState.model_validate_json(json.dumps(checkpoint.state))
    if (
        state.schema_version != config.schema_version
        or not state.approval_resolved
        or state.approval_id is None
        or state.error_code is not None
        or state.final_result is not None
        or state.next_tool is not None
        or state.retry_source_id is not None
    ):
        raise ValueError("Sandbox mutation requires a clean approved checkpoint")
    authorize_sandbox_patch(config.tool_policy, config.tool_policy)
    row = await validate_review_state(session, run_id, state, config)
    proposal = snapshot(row).proposal
    call = (
        await session.scalars(
            select(ToolCallRow).where(
                ToolCallRow.run_id == run_id, ToolCallRow.tool_name == PROPOSAL_TOOL
            )
        )
    ).one()
    inspection = await sandbox_preimage(session, call, proposal)
    return config, SandboxPatchInput(approval_id=row.id, proposal=proposal, inspection=inspection)
