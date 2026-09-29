"""A fixed, versioned execution profile; no arbitrary provider/tool bindings."""

from uuid import UUID

from runveil_core.models import (
    FinalResult,
    FinishAction,
    ModelRequest,
    ModelResponse,
    ProviderError,
    ProviderErrorCode,
    TokenUsage,
    ToolAction,
)
from runveil_core.runtime import (
    ModelPricing,
    ModelRetryPolicy,
    RuntimeConfig,
    RuntimeState,
    execute,
)
from runveil_core.tools import Permission, ToolPolicy, fixture_registry
from runveil_persistence.execution import PostgresExecutionStore, load_runtime_state
from runveil_persistence.jobs import claim_next, enroll
from runveil_persistence.repositories import AgentRepository, RunRepository
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

PROFILE = "fixture-v1"
RETRY_PROFILE = "fixture-retry-v1"
BUDGET_PROFILE = "fixture-budget-v1"
TOKEN_PROFILE = "fixture-token-v1"
COST_PROFILE = "fixture-cost-v1"
POLICY = ToolPolicy(allowed_tools=("fixture.info",), permissions=(Permission.READ,))


def configuration(profile: str = PROFILE) -> RuntimeConfig:
    if profile not in (PROFILE, RETRY_PROFILE, BUDGET_PROFILE, TOKEN_PROFILE, COST_PROFILE):
        raise ValueError("Unknown worker profile")
    if profile in (TOKEN_PROFILE, COST_PROFILE):
        return RuntimeConfig(
            schema_version=6 if profile == COST_PROFILE else 5,
            pricing=ModelPricing(
                price_id="fixture-linear-usd-v1",
                provider="scripted-fixture-cost-v1",
                model="fixture-v1",
                input_nanousd_per_token=1250,
                output_nanousd_per_token=2500,
            )
            if profile == COST_PROFILE
            else None,
            max_cost_nanousd=100_000 if profile == COST_PROFILE else None,
            max_elapsed_seconds=30,
            max_input_tokens=100,
            max_total_output_tokens=100,
            provider="scripted-fixture-cost-v1"
            if profile == COST_PROFILE
            else "scripted-fixture-token-v1",
            model="fixture-v1",
            system_prompt="Identify the fixed public Runveil fixture.",
            tool_policy=POLICY,
            max_steps=5,
            model_retry=ModelRetryPolicy(max_retries=2),
        )
    if profile in (RETRY_PROFILE, BUDGET_PROFILE):
        return RuntimeConfig(
            schema_version=4 if profile == BUDGET_PROFILE else 3,
            max_elapsed_seconds=30 if profile == BUDGET_PROFILE else None,
            provider="scripted-fixture-budget-v1"
            if profile == BUDGET_PROFILE
            else "scripted-fixture-retry-v1",
            model="fixture-v1",
            system_prompt="Identify the fixed public Runveil fixture.",
            tool_policy=POLICY,
            max_steps=5,
            model_retry=ModelRetryPolicy(max_retries=2),
        )
    return RuntimeConfig(
        provider="scripted-fixture-v1",
        model="fixture-v1",
        system_prompt="Identify the fixed public Runveil fixture.",
        tool_policy=POLICY,
        max_steps=3,
    )


class FixtureProvider:
    """Select a deterministic response from durable context, not process memory."""

    async def generate(self, request: ModelRequest) -> ModelResponse:
        action: ToolAction | FinishAction
        if request.messages[-1].role == "tool":
            action = FinishAction(
                action="finish",
                result=FinalResult(summary="Runveil fixture verified.", artifacts=()),
            )
        else:
            action = ToolAction(
                action="tool_call",
                tool_name="fixture.info",
                arguments={},
                decision_summary="Read the fixed public fixture.",
            )
        return ModelResponse(
            model="fixture-v1",
            content=action.model_dump_json(),
            finish_reason="stop",
            latency_ms=0.0,
        )


class RetryFixtureProvider(FixtureProvider):
    """Two known pre-response failures, selected from the durable retry count."""

    def __init__(self, retries_scheduled: int) -> None:
        self.retries_scheduled = retries_scheduled

    async def generate(self, request: ModelRequest) -> ModelResponse:
        if self.retries_scheduled < 2:
            raise ProviderError(ProviderErrorCode.RATE_LIMITED)
        return await super().generate(request)


class TokenFixtureProvider(RetryFixtureProvider):
    """Synthetic usage only; no tokenizer or billing claim."""

    async def generate(self, request: ModelRequest) -> ModelResponse:
        if self.retries_scheduled < 2:
            raise ProviderError(
                ProviderErrorCode.RATE_LIMITED, usage=TokenUsage(input_tokens=0, output_tokens=0)
            )
        response = await FixtureProvider.generate(self, request)
        return response.model_copy(update={"usage": TokenUsage(input_tokens=10, output_tokens=5)})


async def submit(sessions: async_sessionmaker[AsyncSession], *, profile: str = PROFILE) -> UUID:
    """Atomically create and enroll one new fixture run; no broker publication."""
    async with sessions.begin() as session:
        agents = AgentRepository(session)
        agent = await agents.create("Durable fixture demonstration")
        version = await agents.create_version(
            agent.id, configuration(profile).model_dump(mode="json")
        )
        run = await RunRepository(session).create(version.id)
        await enroll(session, run.id, task="Identify the public fixture.", profile=profile)
        return run.id


async def work_once(
    sessions: async_sessionmaker[AsyncSession],
    *,
    run_id: UUID | None = None,
    profile: str = PROFILE,
) -> tuple[UUID, RuntimeState] | None:
    config = configuration(profile)
    claim = await claim_next(sessions, profile=profile, run_id=run_id)
    if claim is None:
        return None
    provider: FixtureProvider = FixtureProvider()
    if profile in (RETRY_PROFILE, BUDGET_PROFILE, TOKEN_PROFILE, COST_PROFILE):
        async with sessions.begin() as session:
            restored = await load_runtime_state(session, claim.run_id)
        provider_type = (
            TokenFixtureProvider
            if profile in (TOKEN_PROFILE, COST_PROFILE)
            else RetryFixtureProvider
        )
        provider = provider_type(restored.retries_scheduled if restored else 0)
    state = await execute(
        claim.run_id,
        claim.task,
        provider_name=config.provider,
        provider=provider,
        tools=fixture_registry(),
        tool_policy=POLICY,
        store=PostgresExecutionStore(sessions, claim=claim, expected_config=config),
        allow_model_retries=profile in (RETRY_PROFILE, BUDGET_PROFILE, TOKEN_PROFILE, COST_PROFILE),
    )
    return claim.run_id, state
