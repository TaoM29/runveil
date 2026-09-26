import json
import traceback

import pytest
from pydantic import ValidationError
from runveil_core.models import (
    FinishAction,
    Message,
    ModelProvider,
    ModelRequest,
    ModelResponse,
    ProviderError,
    ProviderErrorCode,
    TokenUsage,
    ToolAction,
    ToolOffer,
    action_schema,
    validate_response,
)
from runveil_core.scripted import ScriptedProvider

FINISH = '{"action":"finish","result":{"summary":"Done","artifacts":[]}}'
TOOL = (
    '{"action":"tool_call","tool_name":"repository.read_file",'
    '"arguments":{"path":"fixture.py"},"decision_summary":"Inspect fixture"}'
)


def request() -> ModelRequest:
    return ModelRequest(
        model="fixture",
        messages=(Message(role="user", content="Inspect fixture"),),
        available_tools=(
            ToolOffer(
                name="repository.read_file",
                description="Read a fixture",
                input_schema={"type": "object", "properties": {"path": {"type": "string"}}},
            ),
        ),
    )


def response(content: str = FINISH) -> ModelResponse:
    return ModelResponse(
        model="fixture-v1",
        content=content,
        finish_reason="stop",
        usage=TokenUsage(input_tokens=12, output_tokens=8),
        latency_ms=4.0,
    )


@pytest.mark.asyncio
async def test_provider_contract_order_errors_and_detached_history() -> None:
    original = request()
    script: list[ModelResponse | ProviderErrorCode] = [
        response(TOOL),
        ProviderErrorCode.TIMEOUT,
        response(),
    ]
    scripted = ScriptedProvider(script)
    provider: ModelProvider = scripted
    script.clear()
    tool_response = await provider.generate(original)
    action = validate_response(original, tool_response)
    assert isinstance(action, ToolAction) and action.arguments == {"path": "fixture.py"}
    assert tool_response.usage == TokenUsage(input_tokens=12, output_tokens=8)
    assert tool_response.latency_ms == 4.0
    original.available_tools[0].input_schema.clear()
    history = scripted.requests
    assert history[0].available_tools[0].input_schema["type"] == "object"
    history[0].available_tools[0].input_schema.clear()
    assert scripted.requests[0].available_tools[0].input_schema["type"] == "object"
    with pytest.raises(ProviderError) as failure:
        await provider.generate(original)
    assert failure.value.code == ProviderErrorCode.TIMEOUT
    assert str(failure.value) == "provider_timeout"
    assert isinstance(validate_response(original, await provider.generate(original)), FinishAction)
    with pytest.raises(ProviderError) as exhausted:
        await provider.generate(original)
    assert exhausted.value.code == ProviderErrorCode.SCRIPT_EXHAUSTED
    assert len(scripted.requests) == 4  # Includes failed and exhausted calls; no retries.


@pytest.mark.parametrize(
    "content",
    [
        "private fixture text, not JSON",
        "```json\n" + FINISH + "\n```",
        FINISH + FINISH,
        FINISH.replace('"finish"', '"finish","action":"tool_call"'),
        FINISH.replace('"summary":"Done"', '"summary":12'),
        FINISH.replace('"summary":"Done"', '"summary":"Done","reasoning":"private"'),
        TOOL.replace('"fixture.py"', "NaN"),
        TOOL.replace('"fixture.py"', "1e999"),
        TOOL.replace('{"path":"fixture.py"}', "[]"),
        TOOL.replace('"repository.read_file"', '"shell.execute"'),
        '{"action":"finish"}',
    ],
)
def test_untrusted_actions_fail_without_exposing_content(content: str) -> None:
    with pytest.raises(ProviderError) as failure:
        validate_response(request(), response(content))
    assert str(failure.value) == "invalid_response"
    rendered = "".join(traceback.format_exception(failure.value))
    assert content not in rendered


def test_incomplete_outputs_and_contract_constraints() -> None:
    for reason in ("length", "refusal", "other"):
        raw = response().model_dump(mode="json")
        raw["finish_reason"] = reason
        with pytest.raises(ProviderError):
            validate_response(request(), ModelResponse.model_validate(raw))
    for key, value in (
        ("timeout_seconds", 0),
        ("timeout_seconds", float("inf")),
        ("temperature", float("nan")),
        ("max_output_tokens", True),
        ("messages", []),
        ("schema_version", 2),
        ("model", ""),
    ):
        raw_request = request().model_dump(mode="json")
        raw_request[key] = value
        with pytest.raises(ValidationError):
            ModelRequest.model_validate_json(json.dumps(raw_request))
    with pytest.raises(ValidationError):
        ModelRequest(
            model="fixture",
            messages=request().messages,
            available_tools=request().available_tools * 2,
        )
    with pytest.raises(ValidationError):
        Message(role="tool", content="Result")
    with pytest.raises(ValidationError):
        TokenUsage(input_tokens=-1)
    assert TokenUsage().input_tokens is None
    with pytest.raises(ValidationError):
        response("x" * 1_048_577)


def test_contract_json_and_schema_round_trip() -> None:
    original = request()
    assert ModelRequest.model_validate_json(original.model_dump_json()) == original
    assert ModelResponse.model_validate_json(response().model_dump_json()) == response()
    action = validate_response(original, response())
    assert action.model_dump(mode="json") == json.loads(FINISH)
    schema = action_schema()
    assert schema["discriminator"] == {
        "propertyName": "action",
        "mapping": {"finish": "#/$defs/FinishAction", "tool_call": "#/$defs/ToolAction"},
    }
    schema.clear()
    assert action_schema()["discriminator"]
