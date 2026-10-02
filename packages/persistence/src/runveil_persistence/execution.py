"""Short committed runtime boundaries backed by the existing repositories."""

import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from typing import Literal
from uuid import UUID, uuid4

from pydantic import ValidationError
from runveil_core.agents import JsonValue
from runveil_core.approvals import PatchProposal
from runveil_core.errors import InvalidTransition
from runveil_core.models import (
    FinalResult,
    Message,
    ModelRequest,
    ModelResponse,
    TokenUsage,
    validate_response,
)
from runveil_core.mutations import APPLY_TOOL, PatchWriter, authorize_patch
from runveil_core.runs import RunStatus
from runveil_core.runtime import (
    BudgetExceeded,
    CostAccounting,
    Cursor,
    ElapsedBudgetExceeded,
    Pending,
    RuntimeConfig,
    RuntimeState,
    Started,
)
from runveil_core.sandbox import SANDBOX_PROFILE, TEST_TOOL, TestsResult
from runveil_core.sandbox_patch import (
    PATCH_UNKNOWN,
    SANDBOX_PATCH_PROFILE,
    SandboxPatchInput,
    SandboxPatchResult,
    authorize_sandbox_patch,
)
from runveil_core.sandbox_review import SANDBOX_REVIEW_PROFILE, proposal_diff
from runveil_core.sandbox_search import SEARCH_TOOL
from runveil_core.software import SEARCH_PROFILE, SOFTWARE_PROFILE, baseline_failed
from runveil_core.tools import ToolError, ToolPolicy
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from runveil_persistence.history import HistoryRepository, lock_running_run
from runveil_persistence.invocations import InvocationRepository
from runveil_persistence.jobs import Claim, database_now, fence
from runveil_persistence.models import EventRow, JobRow, ModelInvocationRow, ToolCallRow
from runveil_persistence.mutations import authorized_patch
from runveil_persistence.repositories import AgentRepository, RunRepository
from runveil_persistence.sandbox_mutations import authorized_sandbox_patch
from runveil_persistence.sandbox_search import expected_search
from runveil_persistence.worker_approvals import pause_review, prepare_pause, validate_review_state


class ConfigurationRejected(ValueError):
    """Pinned configuration rejected by start before dispatch or history changes."""


class PostgresExecutionStore:
    def __init__(
        self,
        sessions: async_sessionmaker[AsyncSession],
        *,
        claim: Claim | None = None,
        expected_config: RuntimeConfig | None = None,
    ) -> None:
        self.sessions = sessions
        self.claim = claim
        self.expected_config = expected_config

    @asynccontextmanager
    async def _boundary(
        self, cursor: Cursor, *, pending: Pending | None = None, usage: TokenUsage | None = None
    ) -> AsyncIterator[tuple[AsyncSession, float | None]]:
        expired_state: RuntimeState | None = None
        async with self.sessions.begin() as session:
            await fence(session, cursor.run_id, self.claim)
            await lock_running_run(
                session,
                cursor.run_id,
                expected_revision=cursor.revision,
                expected_sequence=cursor.sequence,
            )
            if pending is not None and pending.cursor != cursor:
                raise ValueError("Pending invocation cursor does not match")
            job = await session.get(JobRow, cursor.run_id)
            seconds = (
                (job.deadline_at - await database_now(session)).total_seconds()
                if job is not None and job.deadline_at is not None
                else None
            )
            if seconds is not None and seconds <= 0:
                expired_state = await self._expire(session, cursor, pending, usage)
            else:
                yield session, seconds
        # Raising within the transaction would roll back the terminal evidence.
        if expired_state is not None:
            raise ElapsedBudgetExceeded(expired_state)

    async def remaining_seconds(
        self, cursor: Cursor, *, pending: Pending | None = None
    ) -> float | None:
        async with self._boundary(cursor, pending=pending) as (_, seconds):
            return seconds

    async def _expire(
        self,
        session: AsyncSession,
        cursor: Cursor,
        pending: Pending | None,
        usage: TokenUsage | None,
    ) -> RuntimeState:
        previous = await load_runtime_state(session, cursor.run_id)
        if previous is None:
            raise ValueError("Elapsed expiry requires a runtime checkpoint")
        mutation = (
            await session.get(ToolCallRow, pending.id)
            if pending is not None and pending.kind == "tool"
            else None
        )
        error = (
            PATCH_UNKNOWN
            if previous.schema_version in (14, 15, 16)
            and mutation is not None
            and mutation.tool_name == APPLY_TOOL
            else "elapsed_time_exceeded"
        )
        state = previous.model_copy(
            update={
                "error_code": error,
                "final_result": None,
                "steps_used": previous.steps_used + int(pending is not None),
            }
        )
        if previous.schema_version >= 5 and pending is not None and pending.kind == "model":
            run = await RunRepository(session).get(cursor.run_id)
            version = await AgentRepository(session).get_version(run.agent_version_id)
            config = RuntimeConfig.model_validate_json(version.configuration_json)
            state = state.account_model_usage(usage or TokenUsage(), config)
        if pending is not None:
            invocations = InvocationRepository(session)
            complete = (
                invocations.complete_model if pending.kind == "model" else invocations.complete_tool
            )
            await complete(
                cursor.run_id,
                pending.id,
                state=state.model_dump(mode="json"),
                error_code=error,
                expected_revision=cursor.revision,
                expected_sequence=cursor.sequence,
            )
        else:
            await HistoryRepository(session).record_step(
                cursor.run_id,
                kind="runtime.elapsed_time_exceeded",
                details={},
                state=state.model_dump(mode="json"),
                expected_revision=cursor.revision,
                expected_sequence=cursor.sequence,
            )
        event = EventRow(
            run_id=cursor.run_id,
            kind="budget.exceeded",
            run_revision=cursor.revision,
            payload={"budget": "elapsed_time", "error_code": error},
        )
        session.add(event)
        await session.flush()
        await RunRepository(session).transition(
            cursor.run_id,
            RunStatus.FAILED,
            expected_revision=cursor.revision,
            expected_sequence=event.sequence,
        )
        return state

    async def start(self, run_id: UUID, task: str, provider: str) -> Started:
        async with self.sessions.begin() as session:
            await fence(session, run_id, self.claim)
            runs = RunRepository(session)
            run = await runs.get(run_id)
            if run.status != RunStatus.QUEUED and not (
                self.claim is not None and run.status in (RunStatus.RUNNING, RunStatus.RETRYING)
            ):
                raise InvalidTransition("Execution requires a queued run or claimed recovery")
            if self.claim is not None and task != self.claim.task:
                raise ValueError("Task does not match enrollment")
            version = await AgentRepository(session).get_version(run.agent_version_id)
            try:
                config = RuntimeConfig.model_validate_json(version.configuration_json)
                state = RuntimeState(
                    schema_version=config.schema_version,
                    cost=CostAccounting() if config.schema_version >= 6 else None,
                    messages=(
                        Message(role="system", content=config.system_prompt),
                        Message(role="user", content=task),
                    ),
                )
            except ValidationError:
                raise ConfigurationRejected("Invalid runtime configuration or task") from None
            if config.provider != provider:
                raise ConfigurationRejected(
                    "Provider binding does not match the pinned configuration"
                )
            if (
                config.workspace is not None or config.sandbox is not None
            ) and self.expected_config is None:
                raise ConfigurationRejected("Workspace execution requires a verified binding")
            if config.sandbox is not None and (
                self.claim is None
                or self.claim.profile
                != {
                    12: SANDBOX_PROFILE,
                    13: SANDBOX_REVIEW_PROFILE,
                    14: SANDBOX_PATCH_PROFILE,
                    15: SOFTWARE_PROFILE,
                    16: SEARCH_PROFILE,
                }[config.schema_version]
            ):
                raise ConfigurationRejected("Sandbox execution requires the dedicated profile")
            if self.expected_config is not None and config != self.expected_config:
                raise ConfigurationRejected("Runtime configuration does not match worker profile")
            if (
                config.model_retry.max_retries or config.max_elapsed_seconds
            ) and self.claim is None:
                raise ValueError("Durable retries and elapsed budgets require a worker claim")
            job = await session.get(JobRow, run_id)
            expected_deadline = (
                run.started_at + timedelta(seconds=config.max_elapsed_seconds)
                if run.started_at is not None and config.max_elapsed_seconds is not None
                else None
            )
            if job is not None and job.deadline_at != expected_deadline:
                raise ValueError("Job deadline does not match the pinned run budget")
            if run.status in (RunStatus.RUNNING, RunStatus.RETRYING):
                return await self._resume(
                    session, run_id, run.revision, config, retrying=run.status == RunStatus.RETRYING
                )
            sequence = await session.scalar(
                select(func.max(EventRow.sequence)).where(EventRow.run_id == run_id)
            )
            run = await runs.transition(
                run_id,
                RunStatus.RUNNING,
                expected_revision=run.revision,
                expected_sequence=sequence or 0,
            )
            details: dict[str, JsonValue] = {}
            if config.max_elapsed_seconds is not None:
                assert job is not None and run.started_at is not None
                job.deadline_at = run.started_at + timedelta(seconds=config.max_elapsed_seconds)
                details["deadline_at"] = job.deadline_at.isoformat()
                await session.flush()
            # The transition holds the run lock; its lifecycle event is now the tail.
            sequence = await session.scalar(
                select(func.max(EventRow.sequence)).where(EventRow.run_id == run_id)
            )
            checkpoint = await HistoryRepository(session).record_step(
                run_id,
                kind="runtime.started",
                details=details,
                state=state.model_dump(mode="json"),
                expected_revision=run.revision,
                expected_sequence=sequence or 0,
            )
            return Started(Cursor(run_id, run.revision, checkpoint.event_sequence), config, state)

    async def _resume(
        self,
        session: AsyncSession,
        run_id: UUID,
        revision: int,
        config: RuntimeConfig,
        *,
        retrying: bool = False,
    ) -> Started:
        checkpoint = await HistoryRepository(session).latest_checkpoint(run_id)
        if checkpoint is None or checkpoint.run_revision != revision - int(retrying):
            raise ValueError("Recovery requires a checkpoint at the current revision")
        state = RuntimeState.model_validate_json(json.dumps(checkpoint.state))
        if config.pricing is not None and state.cost != CostAccounting.from_tokens(
            state.tokens, config.pricing
        ):
            raise ValueError("Checkpoint cost differs from pinned pricing and usage")
        if (
            state.schema_version != config.schema_version
            or state.retries_scheduled > config.model_retry.max_retries
            or (state.retry_source_id is not None and state.next_tool is not None)
            or state.final_result is not None
            or state.error_code is not None
            or state.budget_failure(config) is not None
            or state.steps_used > config.max_steps
            or (state.next_tool is None) != (state.source_model_id is None)
        ):
            raise ValueError("Checkpoint is not resumable")
        if state.approval_id is not None:
            if not state.approval_resolved:
                raise ValueError("Pending approval cannot resume execution")
            await validate_review_state(session, run_id, state, config)
        elif state.approval_resolved:
            raise ValueError("Missing approval identity")
        if state.next_tool is not None:
            source = await session.get(ModelInvocationRow, state.source_model_id)
            if (
                source is None
                or source.run_id != run_id
                or source.status != "SUCCEEDED"
                or source.result is None
                or source.step_number != checkpoint.step_number
            ):
                raise ValueError("Invalid checkpoint tool provenance")
            action = validate_response(
                ModelRequest.model_validate_json(json.dumps(source.request)),
                ModelResponse.model_validate_json(json.dumps(source.result)),
            )
            if action != state.next_tool:
                raise ValueError("Checkpoint action differs from its committed model outcome")
        retry_events = list(
            await session.scalars(
                select(EventRow)
                .where(EventRow.run_id == run_id, EventRow.kind == "retry.scheduled")
                .order_by(EventRow.sequence)
            )
        )
        if len(retry_events) != state.retries_scheduled:
            raise ValueError("Checkpoint retry count differs from history")
        if state.retry_source_id is not None:
            source = await session.get(ModelInvocationRow, state.retry_source_id)
            if (
                not retry_events
                or source is None
                or source.run_id != run_id
                or source.status != "FAILED"
                or source.error_code != "provider_rate_limited"
                or retry_events[-1].payload.get("record_id") != str(source.id)
                or retry_events[-1].payload.get("retry_count") != state.retries_scheduled
            ):
                raise ValueError("Invalid retry provenance")
        sequence = await session.scalar(
            select(func.max(EventRow.sequence)).where(EventRow.run_id == run_id)
        )
        cursor = Cursor(run_id, revision, sequence or 0)
        outstanding: list[Pending] = []
        completed_count = 0
        tables: tuple[
            tuple[type[ModelInvocationRow] | type[ToolCallRow], Literal["model", "tool"]], ...
        ] = (
            (ModelInvocationRow, "model"),
            (ToolCallRow, "tool"),
        )
        for table, kind in tables:
            completed_count += (
                await session.scalar(
                    select(func.count())
                    .select_from(table)
                    .where(table.run_id == run_id, table.status != "REQUESTED")
                )
                or 0
            )
            if (
                kind == "model"
                and config.schema_version >= 5
                and state.tokens.attempts != completed_count
            ):
                raise ValueError("Checkpoint token attempt count differs from history")
            records = await session.scalars(
                select(table).where(table.run_id == run_id, table.status == "REQUESTED").limit(2)
            )
            for record in records:
                assert isinstance(record, (ModelInvocationRow, ToolCallRow))
                if record.requested_event_sequence != checkpoint.event_sequence + 1:
                    raise ValueError("Unexpected history after checkpoint")
                outstanding.append(Pending(cursor, record.id, kind))
        if completed_count != state.steps_used:
            raise ValueError("Checkpoint invocation count differs from history")
        if outstanding:
            if (
                retrying
                or len(outstanding) != 1
                or cursor.sequence != checkpoint.event_sequence + 1
                or state.steps_used >= config.max_steps
            ):
                raise ValueError("Ambiguous interrupted execution history")
            if config.schema_version in (14, 15, 16) and state.approval_resolved:
                _, payload = await authorized_sandbox_patch(session, run_id)
                call = await session.get(ToolCallRow, outstanding[0].id)
                if (
                    outstanding[0].kind != "tool"
                    or call is None
                    or call.tool_name != APPLY_TOOL
                    or call.request != payload.model_dump(mode="json")
                ):
                    raise ValueError("Sandbox recovery requires the exact mutation intent")
            return Started(cursor, config, state, outstanding[0])
        if retrying:
            job = await session.get(JobRow, run_id)
            tail = await HistoryRepository(session).events(
                run_id, after_sequence=checkpoint.event_sequence, limit=3
            )
            if (
                state.schema_version < 3
                or state.retry_source_id is None
                or job is None
                or len(tail) != 2
                or tail[0].kind != "retry.scheduled"
                or tail[0].run_revision != revision - 1
                or tail[0].payload.get("record_id") != str(state.retry_source_id)
                or tail[0].payload.get("retry_count") != state.retries_scheduled
                or tail[1].kind != "run.transitioned"
                or tail[1].run_revision != revision
                or tail[1].payload.get("from_status") != "RUNNING"
                or tail[1].payload.get("status") != "RETRYING"
                or datetime.fromisoformat(str(tail[0].payload.get("available_at")))
                != job.available_at
                or (
                    job.available_at > await database_now(session)
                    and (job.deadline_at is None or job.deadline_at > await database_now(session))
                )
            ):
                raise ValueError("Retry schedule is inconsistent or not yet due")
            run = await RunRepository(session).transition(
                run_id,
                RunStatus.RUNNING,
                expected_revision=revision,
                expected_sequence=cursor.sequence,
            )
            resumed = await HistoryRepository(session).record_step(
                run_id,
                kind="runtime.retry_resumed",
                details={},
                state=state.model_dump(mode="json"),
                expected_revision=run.revision,
                expected_sequence=cursor.sequence + 1,
            )
            return Started(Cursor(run_id, run.revision, resumed.event_sequence), config, state)
        if cursor.sequence != checkpoint.event_sequence:
            raise ValueError("Unexpected history after checkpoint")
        return Started(cursor, config, state)

    async def request(
        self,
        cursor: Cursor,
        *,
        kind: Literal["model", "tool"],
        payload: dict[str, JsonValue],
        config: RuntimeConfig,
        model_invocation_id: UUID | None = None,
        tool_name: str | None = None,
    ) -> Pending:
        if (kind == "tool") != (tool_name is not None):
            raise ValueError("Only tool requests require a tool name")
        blocked: RuntimeState | None = None
        async with self._boundary(cursor) as (session, _):
            if tool_name == APPLY_TOOL:
                if config.schema_version in (14, 15, 16):
                    pinned, sandbox_payload = await authorized_sandbox_patch(session, cursor.run_id)
                    expected = sandbox_payload.model_dump(mode="json")
                else:
                    pinned, _, proposal = await authorized_patch(session, cursor.run_id)
                    expected = proposal.model_dump(mode="json")
                if config != pinned or model_invocation_id is not None or payload != expected:
                    raise ValueError("Mutation intent differs from exact approved proposal")
                prior = await session.scalar(
                    select(ToolCallRow.id).where(
                        ToolCallRow.run_id == cursor.run_id, ToolCallRow.tool_name == APPLY_TOOL
                    )
                )
                if prior is not None:
                    raise ValueError("Mutation intent has already been consumed")
            blocked = await self._check_request_budget(session, cursor, kind, tool_name, payload)
            if blocked is None:
                invocations = InvocationRepository(session)
                record_id = uuid4()
                if kind == "model":
                    state = await load_runtime_state(session, cursor.run_id)
                    if state is not None and state.budget_failure(config) is not None:
                        raise ValueError("Run budget does not permit dispatch")
                    model = await invocations.request_model(
                        cursor.run_id,
                        invocation_id=record_id,
                        provider=config.provider,
                        model=config.model,
                        request=payload,
                        retry_of=state.retry_source_id if state is not None else None,
                        expected_revision=cursor.revision,
                        expected_sequence=cursor.sequence,
                    )
                    sequence = model.requested_event_sequence
                else:
                    assert tool_name is not None
                    tool = await invocations.request_tool(
                        cursor.run_id,
                        tool_call_id=record_id,
                        tool_name=tool_name,
                        arguments=payload,
                        model_invocation_id=model_invocation_id,
                        expected_revision=cursor.revision,
                        expected_sequence=cursor.sequence,
                    )
                    sequence = tool.requested_event_sequence
                return Pending(Cursor(cursor.run_id, cursor.revision, sequence), record_id, kind)
        assert blocked is not None
        raise BudgetExceeded(blocked)

    async def _check_request_budget(
        self,
        session: AsyncSession,
        cursor: Cursor,
        kind: Literal["model", "tool"],
        tool_name: str | None,
        arguments: dict[str, JsonValue],
    ) -> RuntimeState | None:
        run = await RunRepository(session).get(cursor.run_id)
        version = await AgentRepository(session).get_version(run.agent_version_id)
        config = RuntimeConfig.model_validate_json(version.configuration_json)
        limit = config.max_model_calls if kind == "model" else config.max_tool_calls
        if limit is not None:
            table = ModelInvocationRow if kind == "model" else ToolCallRow
            count = (
                await session.scalar(
                    select(func.count()).select_from(table).where(table.run_id == cursor.run_id)
                )
                or 0
            )
            if count >= limit:
                return await self._fail_request_budget(
                    session,
                    cursor,
                    budget=f"{kind}_calls",
                    error_code=f"{kind}_call_limit_exceeded",
                    limit=limit,
                    count=count,
                )
        limit = config.max_identical_tool_calls
        if kind != "tool" or limit is None:
            return None
        count = (
            await session.scalar(
                select(func.count())
                .select_from(ToolCallRow)
                .where(
                    ToolCallRow.run_id == cursor.run_id,
                    ToolCallRow.tool_name == tool_name,
                    ToolCallRow.request == arguments,
                )
            )
        ) or 0
        if count < limit:
            return None
        return await self._fail_request_budget(
            session,
            cursor,
            budget="identical_tool_calls",
            error_code="repeated_tool_limit_exceeded",
            limit=limit,
            count=count or 0,
        )

    async def _fail_request_budget(
        self,
        session: AsyncSession,
        cursor: Cursor,
        *,
        budget: str,
        error_code: str,
        limit: int,
        count: int,
    ) -> RuntimeState:
        previous = await load_runtime_state(session, cursor.run_id)
        if previous is None:
            raise ValueError("Invocation limit requires a runtime checkpoint")
        state = previous.model_copy(update={"error_code": error_code})
        await HistoryRepository(session).record_step(
            cursor.run_id,
            kind=f"runtime.{error_code}",
            details={"limit": limit, "prior_calls": count},
            state=state.model_dump(mode="json"),
            expected_revision=cursor.revision,
            expected_sequence=cursor.sequence,
        )
        event = EventRow(
            run_id=cursor.run_id,
            kind="budget.exceeded",
            run_revision=cursor.revision,
            payload={"budget": budget, "error_code": error_code},
        )
        session.add(event)
        await session.flush()
        await RunRepository(session).transition(
            cursor.run_id,
            RunStatus.FAILED,
            expected_revision=cursor.revision,
            expected_sequence=event.sequence,
        )
        return state

    async def complete(
        self,
        pending: Pending,
        state: RuntimeState,
        *,
        result: dict[str, JsonValue] | None = None,
        error_code: str | None = None,
    ) -> Cursor:
        cursor = pending.cursor
        async with self._boundary(
            cursor,
            pending=pending,
            usage=state.tokens.last_usage
            if state.schema_version >= 5 and pending.kind == "model"
            else None,
        ) as (session, _):
            previous = await load_runtime_state(session, cursor.run_id)
            if state.schema_version >= 5:
                if previous is None or state.tokens != (
                    previous.tokens.add(state.tokens.last_usage)
                    if pending.kind == "model"
                    else previous.tokens
                ):
                    raise ValueError("Invalid token accounting boundary")
                run = await RunRepository(session).get(cursor.run_id)
                version = await AgentRepository(session).get_version(run.agent_version_id)
                config = RuntimeConfig.model_validate_json(version.configuration_json)
                if config.pricing is not None and state.cost != CostAccounting.from_tokens(
                    state.tokens, config.pricing
                ):
                    raise ValueError("Outcome cost differs from pinned pricing and usage")
                if state.error_code == "model_call_limit_exceeded" and (
                    pending.kind != "model"
                    or result is not None
                    or config.max_model_calls is None
                    or state.tokens.attempts < config.max_model_calls
                ):
                    raise ValueError("Invalid model-call budget failure")
                failure = state.budget_failure(config)
                if failure is not None and (
                    result is not None
                    or state.final_result is not None
                    or state.error_code not in (failure, "execution_interrupted")
                    or error_code != state.error_code
                ):
                    raise ValueError("Run budget requires a failed outcome")
                if pending.kind == "model" and result is not None:
                    response = ModelResponse.model_validate_json(json.dumps(result))
                    if response.usage != state.tokens.last_usage:
                        raise ValueError("Outcome usage differs from accounting")
            if (
                state.schema_version in (15, 16)
                and previous is not None
                and not previous.approval_resolved
            ):
                if state.final_result is not None:
                    raise ValueError("Software workflow cannot finish before approved validation")
                if pending.kind == "tool" and result is not None:
                    baseline_call = await session.get(ToolCallRow, pending.id)
                    if baseline_call is not None and baseline_call.tool_name == TEST_TOOL:
                        baseline = TestsResult.model_validate_json(json.dumps(result))
                        expected_error = (
                            None if baseline_failed(baseline) else "sandbox_baseline_invalid"
                        )
                        if state.error_code != expected_error:
                            raise ValueError("Baseline outcome differs from workflow state")
            if (
                state.schema_version in (14, 15, 16)
                and previous is not None
                and previous.approval_resolved
            ):
                _, payload = await authorized_sandbox_patch(session, cursor.run_id)
                call = await session.get(ToolCallRow, pending.id)
                if (
                    pending.kind != "tool"
                    or call is None
                    or call.tool_name != APPLY_TOOL
                    or call.request != payload.model_dump(mode="json")
                ):
                    raise ValueError("Sandbox completion requires the exact mutation intent")
                if result is not None:
                    outcome = SandboxPatchResult.model_validate_json(json.dumps(result))
                    if (
                        outcome.proposal_digest != payload.proposal.digest
                        or outcome.before_digest != payload.inspection.digest
                        or outcome.after_digest != payload.postimage().digest
                        or outcome.approved_diff != proposal_diff(payload.proposal)
                        or state.error_code
                        != (
                            None
                            if outcome.tests.status == "passed"
                            else "sandbox_validation_failed"
                        )
                        or (state.final_result is not None) != (outcome.tests.status == "passed")
                    ):
                        raise ValueError("Sandbox outcome differs from approved mutation")
            if state.schema_version == 16 and pending.kind == "tool" and result is not None:
                searched = await session.get(ToolCallRow, pending.id)
                if searched is not None and searched.tool_name == SEARCH_TOOL:
                    expected = await expected_search(session, searched)
                    if result != expected.model_dump(mode="json") or state.error_code is not None:
                        raise ValueError("Search outcome differs from recorded sandbox evidence")
            approval = None
            if state.schema_version in (10, 11, 13, 14, 15, 16):
                approval = await prepare_pause(session, pending, previous, state, config, result)
            invocations = InvocationRepository(session)
            complete = (
                invocations.complete_model if pending.kind == "model" else invocations.complete_tool
            )
            await complete(
                cursor.run_id,
                pending.id,
                state=state.model_dump(mode="json"),
                result=result,
                error_code=error_code,
                expected_revision=cursor.revision,
                expected_sequence=cursor.sequence,
            )
            checkpoint = await HistoryRepository(session).latest_checkpoint(cursor.run_id)
            assert checkpoint is not None
            cursor = Cursor(cursor.run_id, cursor.revision, checkpoint.event_sequence)
            if state.error_code in (
                "token_usage_unknown",
                "token_limit_exceeded",
                "cost_limit_exceeded",
                "model_call_limit_exceeded",
            ):
                event = EventRow(
                    run_id=cursor.run_id,
                    kind="budget.exceeded"
                    if state.error_code != "token_usage_unknown"
                    else "budget.unknown",
                    run_revision=cursor.revision,
                    payload={
                        "budget": {
                            "cost_limit_exceeded": "cost",
                            "model_call_limit_exceeded": "model_calls",
                            "token_limit_exceeded": "tokens",
                            "token_usage_unknown": "tokens",
                        }[state.error_code],
                        "error_code": state.error_code,
                    },
                )
                session.add(event)
                await session.flush()
                cursor = Cursor(cursor.run_id, cursor.revision, event.sequence)
            if approval is not None:
                await validate_review_state(session, cursor.run_id, state, config)
                await pause_review(session, approval, cursor.revision)
            if state.final_result is not None or state.error_code is not None:
                await RunRepository(session).transition(
                    cursor.run_id,
                    RunStatus.FAILED if state.error_code else RunStatus.SUCCEEDED,
                    expected_revision=cursor.revision,
                    expected_sequence=cursor.sequence,
                )
            return cursor

    async def approved_sandbox_patch(self, cursor: Cursor) -> SandboxPatchInput:
        async with self._boundary(cursor) as (session, _):
            _, payload = await authorized_sandbox_patch(session, cursor.run_id)
            return payload

    async def admit_sandbox_patch(self, pending: Pending, operator: ToolPolicy) -> None:
        async with self._boundary(pending.cursor, pending=pending) as (session, _):
            config, payload = await authorized_sandbox_patch(session, pending.cursor.run_id)
            authorize_sandbox_patch(config.tool_policy, operator)
            call = await session.get(ToolCallRow, pending.id)
            if (
                config != self.expected_config
                or pending.kind != "tool"
                or call is None
                or call.run_id != pending.cursor.run_id
                or call.status != "REQUESTED"
                or call.tool_name != APPLY_TOOL
                or call.request != payload.model_dump(mode="json")
                or call.requested_event_sequence != pending.cursor.sequence
            ):
                raise ValueError("Invalid sandbox mutation admission")

    async def approved_patch(self, cursor: Cursor) -> PatchProposal:
        async with self._boundary(cursor) as (session, _):
            _, _, proposal = await authorized_patch(session, cursor.run_id)
            return proposal

    async def apply_patch(
        self, pending: Pending, writer: PatchWriter, operator: ToolPolicy
    ) -> RuntimeState:
        cursor = pending.cursor
        async with self._boundary(cursor, pending=pending) as (session, _):
            config, previous, proposal = await authorized_patch(session, cursor.run_id)
            authorize_patch(config.tool_policy, operator)
            if writer.workspace != config.workspace:
                raise ValueError("Writer workspace differs from approval binding")
            call = await session.get(ToolCallRow, pending.id)
            if (
                pending.kind != "tool"
                or call is None
                or call.run_id != cursor.run_id
                or call.status != "REQUESTED"
                or call.tool_name != APPLY_TOOL
                or call.request != proposal.model_dump(mode="json")
                or call.requested_event_sequence != cursor.sequence
            ):
                raise ValueError("Invalid mutation intent")
            failure: str | None = None
            try:
                # Synchronous under row locks to serialize normal cancellation/claim races.
                writer.apply(proposal)
            except ToolError as exc:
                failure = exc.code.value
            except Exception:
                failure = "patch_outcome_unknown"
            job = await session.get(JobRow, cursor.run_id)
            now = await database_now(session)
            if (
                job is None
                or job.deadline_at is None
                or job.deadline_at <= now
                or job.expires_at is None
                or job.expires_at <= now
            ):
                failure = "patch_outcome_unknown"
            state = previous.model_copy(
                update={
                    "steps_used": previous.steps_used + 1,
                    "error_code": failure,
                    "final_result": None
                    if failure
                    else FinalResult(
                        summary="Applied the exact approved single-file replacement.", artifacts=()
                    ),
                }
            )
            await self._finish_patch(session, pending, state, proposal)
            return state

    async def _finish_patch(
        self, session: AsyncSession, pending: Pending, state: RuntimeState, proposal: PatchProposal
    ) -> None:
        cursor = pending.cursor
        await InvocationRepository(session).complete_tool(
            cursor.run_id,
            pending.id,
            state=state.model_dump(mode="json"),
            result={"applied": True, "digest": proposal.digest}
            if state.error_code is None
            else None,
            error_code=state.error_code,
            expected_revision=cursor.revision,
            expected_sequence=cursor.sequence,
        )
        checkpoint = await HistoryRepository(session).latest_checkpoint(cursor.run_id)
        assert checkpoint is not None
        await RunRepository(session).transition(
            cursor.run_id,
            RunStatus.FAILED if state.error_code else RunStatus.SUCCEEDED,
            expected_revision=cursor.revision,
            expected_sequence=checkpoint.event_sequence,
        )

    async def fail_uncertain_patch(self) -> RuntimeState:
        """Terminal-only recovery, independent of the possibly changed filesystem."""
        if self.claim is None or self.expected_config is None:
            raise ValueError("Mutation recovery requires a claim and pinned configuration")
        started = await self.start(
            self.claim.run_id, self.claim.task, self.expected_config.provider
        )
        pending = started.interrupted
        if pending is None:
            raise ValueError("No interrupted mutation to terminate")
        async with self.sessions.begin() as session:
            await fence(session, pending.cursor.run_id, self.claim)
            await lock_running_run(
                session,
                pending.cursor.run_id,
                expected_revision=pending.cursor.revision,
                expected_sequence=pending.cursor.sequence,
            )
            _, previous, proposal = await authorized_patch(session, pending.cursor.run_id)
            call = await session.get(ToolCallRow, pending.id)
            if (
                pending.kind != "tool"
                or call is None
                or call.tool_name != APPLY_TOOL
                or call.status != "REQUESTED"
                or call.request != proposal.model_dump(mode="json")
            ):
                raise ValueError("Recovery requires the exact outstanding mutation")
            state = previous.model_copy(
                update={
                    "steps_used": previous.steps_used + 1,
                    "error_code": "patch_outcome_unknown",
                }
            )
            await self._finish_patch(session, pending, state, proposal)
            return state

    async def schedule_retry(
        self, pending: Pending, state: RuntimeState, *, error_code: str
    ) -> None:
        cursor = pending.cursor
        async with self._boundary(
            cursor,
            pending=pending,
            usage=state.tokens.last_usage
            if state.schema_version >= 5 and pending.kind == "model"
            else None,
        ) as (session, _):
            run = await RunRepository(session).get(cursor.run_id)
            version = await AgentRepository(session).get_version(run.agent_version_id)
            config = RuntimeConfig.model_validate_json(version.configuration_json)
            previous = await load_runtime_state(session, cursor.run_id)
            if (
                self.claim is None
                or config.schema_version < 3
                or pending.kind != "model"
                or error_code != "provider_rate_limited"
                or previous is None
                or previous.final_result is not None
                or previous.error_code is not None
                or previous.next_tool is not None
                or state.budget_failure(config) is not None
                or state.steps_used >= config.max_steps
                or (
                    config.max_model_calls is not None
                    and state.tokens.attempts >= config.max_model_calls
                )
                or state
                != previous.model_copy(
                    update={
                        "tokens": previous.tokens.add(state.tokens.last_usage)
                        if config.schema_version >= 5
                        else previous.tokens,
                        "cost": CostAccounting.from_tokens(state.tokens, config.pricing)
                        if config.pricing
                        else None,
                        "steps_used": previous.steps_used + 1,
                        "retries_scheduled": previous.retries_scheduled + 1,
                        "retry_source_id": pending.id,
                    }
                )
            ):
                raise ValueError("Invalid retry boundary")
            delay = config.model_retry.delay(state.retries_scheduled)
            await InvocationRepository(session).complete_model(
                cursor.run_id,
                pending.id,
                state=state.model_dump(mode="json"),
                error_code=error_code,
                expected_revision=cursor.revision,
                expected_sequence=cursor.sequence,
            )
            job = await session.get(JobRow, cursor.run_id)
            assert job is not None
            job.available_at = await database_now(session) + timedelta(seconds=delay)
            event = EventRow(
                run_id=cursor.run_id,
                kind="retry.scheduled",
                run_revision=cursor.revision,
                payload={
                    "record_id": str(pending.id),
                    "retry_count": state.retries_scheduled,
                    "available_at": job.available_at.isoformat(),
                },
            )
            session.add(event)
            await session.flush()
            await RunRepository(session).transition(
                cursor.run_id,
                RunStatus.RETRYING,
                expected_revision=cursor.revision,
                expected_sequence=event.sequence,
            )
            job.token = None
            job.expires_at = None
            await session.flush()

    async def exhaust(self, cursor: Cursor, state: RuntimeState) -> None:
        async with self._boundary(cursor) as (session, _):
            checkpoint = await HistoryRepository(session).record_step(
                cursor.run_id,
                kind="runtime.step_limit_exceeded",
                details={"max_steps": state.steps_used},
                state=state.model_dump(mode="json"),
                expected_revision=cursor.revision,
                expected_sequence=cursor.sequence,
            )
            await RunRepository(session).transition(
                cursor.run_id,
                RunStatus.FAILED,
                expected_revision=cursor.revision,
                expected_sequence=checkpoint.event_sequence,
            )


async def load_runtime_state(session: AsyncSession, run_id: UUID) -> RuntimeState | None:
    """Restore evidence, not execution. Read current lifecycle separately."""
    checkpoint = await HistoryRepository(session).latest_checkpoint(run_id)
    if checkpoint is None:
        return None
    return RuntimeState.model_validate_json(json.dumps(checkpoint.state))
