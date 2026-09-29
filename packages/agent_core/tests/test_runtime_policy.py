import json

import pytest
from pydantic import ValidationError
from runveil_core.runtime import ModelPricing, ModelRetryPolicy, RuntimeConfig


def test_retry_policy_bounds_and_explicit_configuration_version() -> None:
    policy = ModelRetryPolicy(max_retries=3, base_delay_seconds=60)
    assert [policy.delay(count) for count in (1, 2, 3)] == [60, 120, 240]
    for count in (0, 4):
        with pytest.raises(ValueError):
            policy.delay(count)
    for encoded in ('{"max_retries":4}', '{"base_delay_seconds":0}', '{"base_delay_seconds":61}'):
        with pytest.raises(ValidationError):
            ModelRetryPolicy.model_validate_json(encoded)
    with pytest.raises(ValidationError):
        RuntimeConfig(
            provider="scripted", model="fixture", system_prompt="Public", model_retry=policy
        )
    legacy = RuntimeConfig.model_validate_json(
        '{"schema_version":2,"provider":"scripted","model":"fixture","system_prompt":"Public"}'
    )
    assert legacy.model_retry.max_retries == 0


def test_elapsed_budget_requires_version_and_bounded_limit() -> None:
    base = {"provider": "scripted", "model": "fixture", "system_prompt": "Public"}
    for version, limit in ((4, None), (3, 30), (4, 0), (4, 86401), (4, True)):
        with pytest.raises(ValidationError):
            RuntimeConfig.model_validate_json(
                json.dumps(base | {"schema_version": version, "max_elapsed_seconds": limit})
            )
    for limit in (1, 86400):
        config = RuntimeConfig.model_validate_json(
            json.dumps(base | {"schema_version": 4, "max_elapsed_seconds": limit})
        )
        assert config.max_elapsed_seconds == limit


def test_token_limits_require_version_five_and_both_strict_limits() -> None:
    base = {
        "provider": "scripted",
        "model": "fixture",
        "system_prompt": "Public",
        "max_elapsed_seconds": 30,
    }
    for version, input_limit, output_limit in (
        (4, 10, 10),
        (5, None, 10),
        (5, 10, None),
        (5, 0, 10),
        (5, 10, True),
        (5, 10, 1_000_000_001),
    ):
        with pytest.raises(ValidationError):
            RuntimeConfig.model_validate_json(
                json.dumps(
                    base
                    | {
                        "schema_version": version,
                        "max_input_tokens": input_limit,
                        "max_total_output_tokens": output_limit,
                    }
                )
            )
    config = RuntimeConfig.model_validate_json(
        json.dumps(
            base
            | {"schema_version": 5, "max_input_tokens": 1, "max_total_output_tokens": 1_000_000_000}
        )
    )
    assert config.max_input_tokens == 1


def test_cost_pricing_requires_complete_matching_snapshot() -> None:
    pricing = ModelPricing(
        price_id="fixture-v1",
        provider="scripted",
        model="fixture",
        input_nanousd_per_token=1250,
        output_nanousd_per_token=2500,
    )
    config = RuntimeConfig(
        schema_version=6,
        provider="scripted",
        model="fixture",
        system_prompt="Public",
        max_elapsed_seconds=30,
        max_input_tokens=100,
        max_total_output_tokens=100,
        pricing=pricing,
        max_cost_nanousd=100_000,
    )
    base = config.model_dump(mode="json")
    for update in (
        {"pricing": None},
        {"max_cost_nanousd": None},
        {"max_cost_nanousd": 0},
        {"max_cost_nanousd": True},
        {"max_cost_nanousd": 1_000_000_000_000_001},
        {"schema_version": 5},
    ):
        with pytest.raises(ValidationError):
            RuntimeConfig.model_validate_json(json.dumps(base | update))
    for price_update in (
        {"provider": "other"},
        {"model": "other"},
        {"currency": "EUR"},
        {"input_nanousd_per_token": None},
        {"input_nanousd_per_token": 0.5},
        {"input_nanousd_per_token": True},
        {"input_nanousd_per_token": -1},
        {"output_nanousd_per_token": 1_000_000_001},
    ):
        with pytest.raises(ValidationError):
            RuntimeConfig.model_validate_json(
                json.dumps(base | {"pricing": pricing.model_dump(mode="json") | price_update})
            )


def test_cost_is_exact_and_partial_usage_remains_unknown_even_at_zero_rates() -> None:
    from runveil_core.models import TokenUsage
    from runveil_core.runtime import CostAccounting, ModelPricing, TokenAccounting

    price = ModelPricing(
        price_id="fractional-cent",
        provider="scripted",
        model="fixture",
        input_nanousd_per_token=3,
        output_nanousd_per_token=7,
    )
    tokens = TokenAccounting().add(TokenUsage(input_tokens=1, output_tokens=1))
    tokens = tokens.add(TokenUsage(input_tokens=2, output_tokens=3))
    assert CostAccounting.from_tokens(tokens, price).known_nanousd == 37
    tokens = tokens.add(TokenUsage(input_tokens=5))
    cost = CostAccounting.from_tokens(tokens, price)
    assert cost.known_nanousd == 52 and cost.unknown_attempts == 1
    free = price.model_copy(update={"input_nanousd_per_token": 0, "output_nanousd_per_token": 0})
    assert CostAccounting.from_tokens(tokens, free).unknown_attempts == 1
    assert CostAccounting.from_tokens(tokens, free).known_nanousd == 0


def test_repeated_tool_limit_requires_version_seven_and_strict_bounds() -> None:
    base = RuntimeConfig(
        schema_version=6,
        provider="scripted",
        model="fixture",
        system_prompt="Public",
        max_elapsed_seconds=30,
        max_input_tokens=100,
        max_total_output_tokens=100,
        pricing=ModelPricing(
            price_id="fixture",
            provider="scripted",
            model="fixture",
            input_nanousd_per_token=0,
            output_nanousd_per_token=0,
        ),
        max_cost_nanousd=100,
    ).model_dump(mode="json")
    for version, limit in ((7, None), (6, 2), (7, 0), (7, 65), (7, True), (7, 1.5)):
        with pytest.raises(ValidationError):
            RuntimeConfig.model_validate_json(
                json.dumps(base | {"schema_version": version, "max_identical_tool_calls": limit})
            )
    for limit in (1, 64):
        assert (
            RuntimeConfig.model_validate_json(
                json.dumps(base | {"schema_version": 7, "max_identical_tool_calls": limit})
            ).max_identical_tool_calls
            == limit
        )


def test_invocation_limits_require_version_eight_and_both_strict_caps() -> None:
    base = RuntimeConfig(
        schema_version=7,
        provider="scripted",
        model="fixture",
        system_prompt="Public",
        max_elapsed_seconds=30,
        max_input_tokens=100,
        max_total_output_tokens=100,
        max_identical_tool_calls=2,
        pricing=ModelPricing(
            price_id="fixture",
            provider="scripted",
            model="fixture",
            input_nanousd_per_token=0,
            output_nanousd_per_token=0,
        ),
        max_cost_nanousd=100,
    ).model_dump(mode="json")
    for version, model, tool in (
        (7, 1, 1),
        (8, None, 1),
        (8, 1, None),
        (8, -1, 1),
        (8, 1, 65),
        (8, True, 1),
        (8, 1, 1.5),
    ):
        with pytest.raises(ValidationError):
            RuntimeConfig.model_validate_json(
                json.dumps(
                    base
                    | {"schema_version": version, "max_model_calls": model, "max_tool_calls": tool}
                )
            )
    for model, tool in ((0, 64), (64, 0)):
        config = RuntimeConfig.model_validate_json(
            json.dumps(
                base | {"schema_version": 8, "max_model_calls": model, "max_tool_calls": tool}
            )
        )
        assert (config.max_model_calls, config.max_tool_calls) == (model, tool)
