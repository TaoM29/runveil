# Model contracts — Phase 2A

The core package exposes an async `ModelProvider.generate(ModelRequest)` protocol
and an offline scripted implementation. No HTTP endpoint, hosted adapter, runtime
loop or credentials are needed. Install with `uv sync --locked --all-packages`.

```python
from runveil_core.models import (
    FinishAction,
    Message,
    ModelProvider,
    ModelRequest,
    ModelResponse,
    validate_response,
)
from runveil_core.scripted import ScriptedProvider


async def example() -> str:
    request = ModelRequest(
        model="fixture",
        messages=(Message(role="user", content="Finish the fixture"),),
        max_output_tokens=256,
        timeout_seconds=30.0,
    )
    provider: ModelProvider = ScriptedProvider(
        [
            ModelResponse(
                model="fixture",
                content='{"action":"finish","result":{"summary":"Done","artifacts":[]}}',
                finish_reason="stop",
                latency_ms=0.0,
            ),
        ]
    )
    response = await provider.generate(request)
    action = validate_response(request, response)
    assert isinstance(action, FinishAction)
    return action.result.summary
```

`action_schema()` returns a fresh JSON Schema for the fixed action envelope. A
request advertises `ToolOffer` values (name, description, input-schema JSON object).
Tool actions must name an advertised tool and carry object arguments plus a short
`decision_summary`. Finish actions require a result summary and artifact-reference
array (possibly empty). References are data only. Only `finish_reason="stop"` may
produce a usable action. Raw text, Markdown fences, extra fields, duplicate keys,
non-finite numbers, invalid types and unknown actions are rejected, without repair.

Model response `content` contains the action JSON. Native vendor tool calls are
not a second action path in this slice; a later adapter must normalize them or
reject unsupported modes. Response `model` may be the resolved model identifier
rather than the request alias. Usage counters are individually nullable and cannot
be negative; unknown usage must never be reported as zero. Latency is milliseconds
supplied by the provider, independent of persistence timestamps.

Contracts reject unknown fields and scalar coercions. Messages/content are bounded
to 1,048,576 characters each, requests to 256 messages/128 unique tools, summaries
and artifact references to smaller field limits. These are initial contract bounds,
not token-budget enforcement or a total HTTP-body limit. Tool schemas are only
JSON objects here; supported dialect, argument validation, permissions and side
effects are future tool-runtime responsibilities. Model names use printable ASCII
identifiers with `.`, `_`, `:`, `/` and `-`. Hosted adapters must explicitly handle
vendor limitations rather than silently changing requested settings.

A script contains `ModelResponse` or `ProviderErrorCode` entries. Every call records
a detached request and consumes one entry. Errors consume an entry; exhaustion
raises `script_exhausted` and records the attempted call. There is no retry,
sleep, clock measurement or network call. `requests` returns fresh copies for
assertions. Use one script per ordered test consumer. Responses with malformed
content can deliberately exercise validation failures. Provider exceptions expose
fixed codes suitable for Phase 1C `error_code`; no raw body/exception is accepted.
`validate_response` converts content-validation failures to `invalid_response`.
Local contract-construction mistakes raise Pydantic validation errors; do not log
those with sensitive inputs.

Field assignment is frozen, but nested JSON dictionaries are mutable caller data.
Serialize at retention boundaries. Scripted fixtures and captured request history
are serialized snapshots; Phase 1 persistence already detaches input JSON. Use
`model_dump(mode="json")` for repository inputs and `model_validate_json` for
restoration. Never store credentials or hidden reasoning, and select safe content
before persistence; these types are not automatic redaction.

The caller explicitly validates a generated response before using or persisting
it as a successful action. The protocol does not start a transaction, transition a
run, authorize a tool or make a pending invocation safe to retry. See
[ADR 0006](../adr/0006-model-contracts.md) and
[persistence operations](PERSISTENCE.md).

Run the offline contract checks with:

```sh
uv run pytest packages/agent_core/tests/test_models.py
# With the test database configured as in README:
uv run pytest packages/persistence/tests/test_invocations.py -k normalized
```

Phase 2B adds real transport, actual timeout/cancellation handling, error mapping,
adapter contract tests and an explicitly opt-in live check. No live invocation or
full Phase 2 completion is claimed here.
