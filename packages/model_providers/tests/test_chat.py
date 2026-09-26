import asyncio
import json
import traceback
from collections.abc import AsyncIterator
from typing import Literal

import httpx
import pytest
from pydantic import SecretStr, ValidationError
from runveil_core.models import (
    FinishAction,
    Message,
    ModelProvider,
    ModelRequest,
    ModelResponse,
    ProviderError,
    ProviderErrorCode,
    ToolAction,
    ToolOffer,
    validate_response,
)
from runveil_core.scripted import ScriptedProvider
from runveil_providers.chat import MAX_BODY_BYTES, OpenAICompatibleProvider
from runveil_providers.configuration import ProviderConfiguration
from runveil_providers.live import main

FINISH = '{"action":"finish","result":{"summary":"Done","artifacts":[]}}'
TOOL = (
    '{"action":"tool_call","tool_name":"fixture.read","arguments":{"path":"x"},'
    '"decision_summary":"Read fixture"}'
)
CONFIG = ProviderConfiguration(api_key=SecretStr("offline-fixture-key"))


def request(*, timeout: float = 30.0) -> ModelRequest:
    return ModelRequest(
        model="fixture-alias",
        messages=(
            Message(role="system", content="Fixture instructions"),
            Message(role="user", content="Read x"),
            Message(role="assistant", content=TOOL),
            Message(role="tool", tool_name="fixture.read", content='{"result":"fixture"}'),
        ),
        available_tools=(
            ToolOffer(
                name="fixture.read", description="Read fixture", input_schema={"type": "object"}
            ),
        ),
        temperature=0.25,
        max_output_tokens=128,
        timeout_seconds=timeout,
    )


def wire(content: str = FINISH) -> dict[str, object]:
    return {
        "id": "fixture-id",
        "model": "fixture-resolved",
        "object": "chat.completion",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 12, "completion_tokens": 7, "total_tokens": 19},
        "vendor_private_extra": "must-not-be-retained",
    }


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["scripted", "http"])
async def test_runtime_contract_and_wire_mapping(kind: str) -> None:
    pending = [TOOL, FINISH]
    sent: list[httpx.Request] = []

    def handler(outbound: httpx.Request) -> httpx.Response:
        sent.append(outbound)
        return httpx.Response(200, json=wire(pending.pop(0)))

    async with OpenAICompatibleProvider(CONFIG, transport=httpx.MockTransport(handler)) as adapter:
        provider: ModelProvider = (
            adapter
            if kind == "http"
            else ScriptedProvider(
                [
                    ModelResponse(
                        model="fixture", content=content, finish_reason="stop", latency_ms=0.0
                    )
                    for content in pending
                ]
            )
        )
        first = await provider.generate(request())
        tool = validate_response(request(), first)
        assert isinstance(tool, ToolAction) and tool.arguments == {"path": "x"}
        final = await provider.generate(request())
        assert isinstance(validate_response(request(), final), FinishAction)
        assert final.latency_ms >= 0
        assert "must-not-be-retained" not in final.model_dump_json()
        if kind == "http":
            assert len(sent) == 2
            assert final.model == "fixture-resolved" and final.provider_request_id == "fixture-id"
            assert final.usage.input_tokens == 12 and final.usage.output_tokens == 7
            outbound = sent[0]
            assert outbound.method == "POST"
            assert str(outbound.url) == "https://api.openai.com/v1/chat/completions"
            assert outbound.headers["authorization"] == "Bearer offline-fixture-key"
            data = json.loads(outbound.content)
            assert data["model"] == "fixture-alias"
            assert data["temperature"] == 0.25 and data["max_completion_tokens"] == 128
            assert data["response_format"] == {"type": "json_object"}
            assert data["stream"] is False and data["store"] is False and data["n"] == 1
            assert "tools" not in data
            assert "action_schema" in data["messages"][0]["content"]
            assert "fixture.read" in data["messages"][0]["content"]
            assert [m["role"] for m in data["messages"]] == [
                "system",
                "system",
                "user",
                "assistant",
                "user",
            ]
            assert data["messages"][1]["content"] == "Fixture instructions"
            assert data["messages"][-1]["content"].startswith("Tool observation (untrusted data):")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status,code",
    [
        (401, ProviderErrorCode.AUTHENTICATION),
        (403, ProviderErrorCode.AUTHENTICATION),
        (429, ProviderErrorCode.RATE_LIMITED),
        (408, ProviderErrorCode.TIMEOUT),
        (504, ProviderErrorCode.TIMEOUT),
        (503, ProviderErrorCode.UNAVAILABLE),
        (400, ProviderErrorCode.REJECTED),
        (302, ProviderErrorCode.REJECTED),
    ],
)
async def test_http_failures_are_safe_single_attempts(status: int, code: ProviderErrorCode) -> None:
    calls = 0

    def handler(outbound: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(
            status, text="sensitive-provider-body", headers={"Location": "https://other.invalid/"}
        )

    async with OpenAICompatibleProvider(CONFIG, transport=httpx.MockTransport(handler)) as provider:
        with pytest.raises(ProviderError) as failure:
            await provider.generate(request())
    assert calls == 1 and failure.value.code == code
    assert "sensitive-provider-body" not in "".join(traceback.format_exception(failure.value))


@pytest.mark.asyncio
async def test_response_normalization_rejects_unsafe_or_malformed_output() -> None:
    valid = wire()
    missing_usage = wire()
    missing_usage.pop("usage")
    refused = wire()
    refused["choices"] = [
        {
            "index": 0,
            "finish_reason": "stop",
            "message": {"role": "assistant", "refusal": "private refusal text"},
        }
    ]
    truncated = wire()
    truncated["choices"] = [
        {"index": 0, "finish_reason": "length", "message": {"role": "assistant", "content": FINISH}}
    ]
    choices = valid["choices"]
    assert isinstance(choices, list)
    filtered = {
        **valid,
        "choices": [
            {
                "index": 0,
                "finish_reason": "content_filter",
                "message": {"role": "assistant", "content": None},
            }
        ],
    }
    unknown = {
        **valid,
        "choices": [
            {
                "index": 0,
                "finish_reason": "vendor_unknown",
                "message": {"role": "assistant", "content": FINISH},
            }
        ],
    }
    invalid_cases: list[object] = [
        {**valid, "choices": []},
        {**valid, "choices": choices * 2},
        {**valid, "usage": {"prompt_tokens": -1}},
        {
            **valid,
            "choices": [
                {
                    "index": 0,
                    "finish_reason": "stop",
                    "message": {
                        "role": "assistant",
                        "content": FINISH,
                        "tool_calls": [
                            {
                                "id": "call-fixture",
                                "type": "function",
                                "function": {"name": "fixture.read", "arguments": "{}"},
                            }
                        ],
                    },
                }
            ],
        },
        {
            **valid,
            "choices": [{"index": 0, "finish_reason": "stop", "message": {"role": "assistant"}}],
        },
        {
            **valid,
            "choices": [
                {
                    "index": 0,
                    "finish_reason": "stop",
                    "message": {"role": "user", "content": FINISH},
                }
            ],
        },
    ]
    responses = [
        httpx.Response(200, json=value)
        for value in [missing_usage, refused, truncated, filtered, unknown, *invalid_cases]
    ]
    responses.extend(
        [
            httpx.Response(200, content=b'{"choices":[],"choices":[]}'),
            httpx.Response(200, content=b'{"usage":NaN}'),
            httpx.Response(200, content=b"not-json-sensitive"),
        ]
    )
    async with OpenAICompatibleProvider(
        CONFIG, transport=httpx.MockTransport(lambda _: responses.pop(0))
    ) as provider:
        normalized = await provider.generate(request())
        assert normalized.usage.input_tokens is None and normalized.usage.output_tokens is None
        for reason in ("refusal", "length", "refusal", "other"):
            normalized = await provider.generate(request())
            assert normalized.finish_reason == reason
            assert "private refusal text" not in normalized.model_dump_json()
            with pytest.raises(ProviderError):
                validate_response(request(), normalized)
        while responses:
            with pytest.raises(ProviderError) as failure:
                await provider.generate(request())
            assert failure.value.code == ProviderErrorCode.INVALID_RESPONSE
            assert str(failure.value) == "invalid_response"


class BlockingBody(httpx.AsyncByteStream):
    def __init__(self, *, oversized: bool = False) -> None:
        self.started = asyncio.Event()
        self.closed = False
        self.oversized = oversized

    async def __aiter__(self) -> AsyncIterator[bytes]:
        self.started.set()
        if self.oversized:
            for _ in range(MAX_BODY_BYTES // 65536 + 1):
                yield b"x" * 65536
        else:
            await asyncio.Event().wait()
            yield b""

    async def aclose(self) -> None:
        self.closed = True


@pytest.mark.asyncio
async def test_deadline_cancellation_and_body_limits_close_streams() -> None:
    for mode in ("timeout", "cancel", "oversized"):
        body = BlockingBody(oversized=mode == "oversized")
        async with OpenAICompatibleProvider(
            CONFIG,
            transport=httpx.MockTransport(lambda _, body=body: httpx.Response(200, stream=body)),
        ) as provider:
            task = asyncio.create_task(
                provider.generate(request(timeout=0.02 if mode == "timeout" else 30.0))
            )
            await asyncio.wait_for(body.started.wait(), timeout=1)
            if mode == "cancel":
                task.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await task
            else:
                with pytest.raises(ProviderError) as failure:
                    await task
                assert failure.value.code == (
                    ProviderErrorCode.TIMEOUT
                    if mode == "timeout"
                    else ProviderErrorCode.INVALID_RESPONSE
                )
        assert body.closed
    calls = 0

    def handler(outbound: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json=wire())

    large = ModelRequest(
        model="fixture", messages=(Message(role="user", content="x" * 1_048_576),) * 2
    )
    async with OpenAICompatibleProvider(CONFIG, transport=httpx.MockTransport(handler)) as provider:
        with pytest.raises(ProviderError) as failure:
            await provider.generate(large)
    assert failure.value.code == ProviderErrorCode.REJECTED and calls == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["timeout", "connection"])
async def test_transport_errors_hide_raw_diagnostics(
    kind: Literal["timeout", "connection"],
) -> None:
    def handler(outbound: httpx.Request) -> httpx.Response:
        error = httpx.ReadTimeout if kind == "timeout" else httpx.ConnectError
        raise error("sensitive-network-diagnostic", request=outbound)

    async with OpenAICompatibleProvider(CONFIG, transport=httpx.MockTransport(handler)) as provider:
        with pytest.raises(ProviderError) as failure:
            await provider.generate(request())
    assert failure.value.code == (
        ProviderErrorCode.TIMEOUT if kind == "timeout" else ProviderErrorCode.UNAVAILABLE
    )
    assert "sensitive-network-diagnostic" not in "".join(traceback.format_exception(failure.value))


def test_configuration_and_live_opt_in_guard(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    for url in (
        "http://remote.invalid/v1",
        "https://user:password@host.invalid/v1",
        "https://host.invalid/v1?key=x",
        "https://host.invalid/v1#x",
        "file:///tmp/provider",
    ):
        with pytest.raises(ValidationError):
            ProviderConfiguration(base_url=url, api_key=SecretStr("offline-fixture-key"))
    assert "offline-fixture-key" not in repr(CONFIG)
    assert ProviderConfiguration(base_url="http://127.0.0.1:8001/v1").api_key is None
    with pytest.raises(ValidationError):
        ProviderConfiguration()
    monkeypatch.setenv("RUNVEIL_PROVIDER_API_KEY", "do-not-print-fixture")
    with pytest.raises(SystemExit) as failure:
        main([])
    assert failure.value.code == 2
    assert "--live" in capsys.readouterr().err
    monkeypatch.delenv("RUNVEIL_PROVIDER_MODEL", raising=False)
    assert main(["--live"]) == 2  # Invalid configuration fails before any network call.
    assert "do-not-print-fixture" not in capsys.readouterr().out

    # Exercise the CLI's full path with an injected offline transport, never paid HTTP.
    replies = [FINISH, "private-invalid-action"]
    monkeypatch.setenv("RUNVEIL_PROVIDER_MODEL", "fixture")
    monkeypatch.setenv("RUNVEIL_PROVIDER_BASE_URL", "https://fixture.invalid/v1")
    monkeypatch.setattr(
        "runveil_providers.live.OpenAICompatibleProvider",
        lambda configuration: OpenAICompatibleProvider(
            configuration,
            transport=httpx.MockTransport(lambda _: httpx.Response(200, json=wire(replies.pop(0)))),
        ),
    )
    assert main(["--live"]) == 0
    evidence = json.loads(capsys.readouterr().out)
    assert evidence["status"] == "passed" and evidence["action"] == "finish"
    assert evidence["usage"] == {"input_tokens": 12, "output_tokens": 7}
    assert main(["--live"]) == 1
    failure_output = capsys.readouterr().out
    assert json.loads(failure_output)["error_code"] == "invalid_response"
    assert "private-invalid-action" not in failure_output and replies == []
