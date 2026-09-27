import json

import pytest
from pydantic import ValidationError
from runveil_core.runtime import ModelRetryPolicy, RuntimeConfig


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
