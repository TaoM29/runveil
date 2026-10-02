"""Independent search provenance over the recorded sandbox snapshot; no filesystem I/O."""

import json

from runveil_core.models import ModelRequest, ModelResponse, ToolAction, validate_response
from runveil_core.runtime import RuntimeConfig
from runveil_core.sandbox_review import INSPECT_TOOL, InspectionResult, validate_inspection
from runveil_core.sandbox_search import SEARCH_TOOL, SearchInput, SearchResult, search_snapshot
from runveil_core.software import SEARCH_PROFILE
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from runveil_persistence.models import JobRow, ModelInvocationRow, ToolCallRow
from runveil_persistence.repositories import AgentRepository, RunRepository


async def expected_search(session: AsyncSession, call: ToolCallRow) -> SearchResult:
    run = await RunRepository(session).get(call.run_id)
    version = await AgentRepository(session).get_version(run.agent_version_id)
    config = RuntimeConfig.model_validate_json(version.configuration_json)
    job = await session.get(JobRow, call.run_id)
    source = await session.get(ModelInvocationRow, call.model_invocation_id)
    inspections = list(
        await session.scalars(
            select(ToolCallRow)
            .where(ToolCallRow.run_id == call.run_id, ToolCallRow.tool_name == INSPECT_TOOL)
            .limit(2)
        )
    )
    if (
        config.schema_version != 16
        or config.sandbox is None
        or job is None
        or job.profile != SEARCH_PROFILE
        or call.tool_name != SEARCH_TOOL
        or len(inspections) != 1
        or source is None
        or source.run_id != call.run_id
        or source.status != "SUCCEEDED"
        or source.result is None
        or source.completed_event_sequence is None
    ):
        raise ValueError("Search requires its pinned profile and recorded inspection")
    inspected = inspections[0]
    if (
        inspected.status != "SUCCEEDED"
        or inspected.request != {}
        or inspected.result is None
        or inspected.completed_event_sequence is None
        or not (
            inspected.completed_event_sequence
            < source.requested_event_sequence
            < source.completed_event_sequence
            < call.requested_event_sequence
        )
    ):
        raise ValueError("Search must follow the completed inspection")
    snapshot = InspectionResult.model_validate_json(json.dumps(inspected.result))
    validate_inspection(snapshot, config.sandbox.fixture)
    request = ModelRequest.model_validate_json(json.dumps(source.request))
    action = validate_response(
        request, ModelResponse.model_validate_json(json.dumps(source.result))
    )
    observations = [m for m in request.messages if m.role == "tool"]
    if (
        len(observations) != 1
        or observations[0].tool_name != INSPECT_TOOL
        or InspectionResult.model_validate_json(observations[0].content) != snapshot
        or not isinstance(action, ToolAction)
        or action.tool_name != SEARCH_TOOL
        or action.arguments != call.request
    ):
        raise ValueError("Search differs from its model action or inspection context")
    return search_snapshot(snapshot, SearchInput.model_validate(call.request))


async def validate_search_chain(
    session: AsyncSession,
    baseline: ToolCallRow,
    baseline_request: ModelRequest,
    proposal_request: ModelRequest,
) -> None:
    calls = list(
        await session.scalars(
            select(ToolCallRow)
            .where(ToolCallRow.run_id == baseline.run_id, ToolCallRow.tool_name == SEARCH_TOOL)
            .limit(2)
        )
    )
    source = await session.get(ModelInvocationRow, baseline.model_invocation_id)
    if (
        len(calls) != 1
        or source is None
        or calls[0].status != "SUCCEEDED"
        or calls[0].completed_event_sequence is None
        or calls[0].completed_event_sequence >= source.requested_event_sequence
    ):
        raise ValueError("Baseline requires one completed search before generation")
    call = calls[0]
    expected = await expected_search(session, call)
    if call.result != expected.model_dump(mode="json"):
        raise ValueError("Recorded search differs from the pinned snapshot")
    for request in (baseline_request, proposal_request):
        observations = [
            m for m in request.messages if m.role == "tool" and m.tool_name == SEARCH_TOOL
        ]
        if (
            len(observations) != 1
            or SearchResult.model_validate_json(observations[0].content) != expected
        ):
            raise ValueError("Model context differs from the recorded search")
