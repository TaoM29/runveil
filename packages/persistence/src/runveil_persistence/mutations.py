"""Pinned approval validation shared by mutation admission and dispatch."""

import json
from uuid import UUID

from runveil_core.approvals import PatchProposal
from runveil_core.mutations import PATCH_PROFILE, authorize_patch
from runveil_core.runtime import RuntimeConfig, RuntimeState
from sqlalchemy.ext.asyncio import AsyncSession

from runveil_persistence.approvals import snapshot
from runveil_persistence.history import HistoryRepository
from runveil_persistence.models import JobRow
from runveil_persistence.repositories import AgentRepository, RunRepository
from runveil_persistence.worker_approvals import validate_review_state


async def authorized_patch(
    session: AsyncSession, run_id: UUID
) -> tuple[RuntimeConfig, RuntimeState, PatchProposal]:
    run = await RunRepository(session).get(run_id)
    version = await AgentRepository(session).get_version(run.agent_version_id)
    config = RuntimeConfig.model_validate_json(version.configuration_json)
    job = await session.get(JobRow, run_id)
    checkpoint = await HistoryRepository(session).latest_checkpoint(run_id)
    if (
        config.schema_version != 11
        or job is None
        or job.profile != PATCH_PROFILE
        or checkpoint is None
    ):
        raise ValueError("Mutation requires the pinned patch profile")
    state = RuntimeState.model_validate_json(json.dumps(checkpoint.state))
    if (
        state.schema_version != 11
        or not state.approval_resolved
        or state.approval_id is None
        or state.error_code is not None
        or state.final_result is not None
        or state.next_tool is not None
        or state.retry_source_id is not None
    ):
        raise ValueError("Mutation requires a clean approved checkpoint")
    authorize_patch(config.tool_policy, config.tool_policy)
    row = await validate_review_state(session, run_id, state, config)
    return config, state, snapshot(row).proposal
