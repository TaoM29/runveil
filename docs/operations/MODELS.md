# Model contracts and providers — Phase 2B

The core package exposes an async `ModelProvider.generate(ModelRequest)` protocol
and an offline scripted implementation. The `runveil_providers` package adds a
hosted OpenAI-compatible HTTP adapter. Neither starts a runtime loop or exposes
an application HTTP endpoint. Install with `uv sync --locked --all-packages`.
The following scripted example needs no credentials:

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
not a second action path: the HTTP adapter rejects nonempty native tool calls and
legacy function calls. Response `model` may be the resolved model identifier
rather than the request alias. Usage counters are individually nullable and cannot
be negative; unknown usage must never be reported as zero. `ProviderError` may
also carry normalized `TokenUsage` through its optional `usage` argument. Omitted
error usage remains unknown; HTTP status alone never establishes zero consumption. Latency is milliseconds
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

## Hosted adapter

Use `OpenAICompatibleProvider` as an async context manager, or explicitly call
`aclose()` when its lifetime ends. It owns the client. Keep provider configuration
outside persisted agent versions, model requests and checkpoint state:

```python
import os

from pydantic import SecretStr
from runveil_providers.chat import OpenAICompatibleProvider
from runveil_providers.configuration import ProviderConfiguration


async def hosted_example(request: ModelRequest) -> str:
    configuration = ProviderConfiguration(
        base_url=os.environ.get("RUNVEIL_PROVIDER_BASE_URL", "https://api.openai.com/v1"),
        api_key=SecretStr(os.environ["RUNVEIL_PROVIDER_API_KEY"]),
    )
    async with OpenAICompatibleProvider(configuration) as provider:
        response = await provider.generate(request)
        action = validate_response(request, response)
        return action.action
```

The URL identifies the API base (e.g. `/v1`), not the full completions endpoint.
The adapter appends `chat/completions`. Configuration requires HTTPS and a key for
remote hosts. Literal loopback/localhost permits HTTP and an absent key for local
compatible services. Credentials in URLs, queries and fragments are rejected.
Redirects, environment proxy settings and netrc inheritance are disabled. This
configuration is trusted operator input, not an end-user URL or an SSRF boundary.
Do not put secrets in URL paths. Local validation errors should not be logged with
sensitive inputs; the live command prints only fixed error codes.

The supported profile is deliberately narrow: one non-streaming Chat Completions
choice, `response_format={"type":"json_object"}`, `temperature`,
`max_completion_tokens`, `n=1` and `store=false`. Select a model/endpoint supporting
these parameters. Settings are never silently dropped or retried with alternatives.
No universal compatibility with every model or OpenAI-like service is claimed.
OpenAI is the default hosted endpoint; alternate endpoints use the same adapter.

A prepended system message supplies the core JSON action schema and advertised
tool descriptions/schemas. Original text message order is preserved. Core tool
observations have no native call IDs, so they become labelled JSON data in user
messages. This labelling helps context interpretation but is not an authorization
or prompt-injection security boundary. No native tool is registered or executed.

The adapter explicitly chooses JSON mode plus local validation. The current action
schema has a root union and open-ended arguments and cannot be sent unchanged to
OpenAI strict Structured Outputs. JSON mode does not guarantee schema adherence;
`validate_response` must succeed before an action can be used. See the
[official structured-output guide](https://developers.openai.com/api/docs/guides/structured-outputs)
and [ADR 0007](../adr/0007-hosted-provider.md).

Requests and decoded response bodies are limited to 2 MiB; oversized requests
fail before dispatch. This caps accumulated payloads, not all parsing/decompression
memory. A whole-network-operation deadline uses `timeout_seconds` in addition to
HTTPX's operation timeouts. Cancellation propagates and closes the response stream.
Latency is measured with a monotonic clock through body reading, not database
timestamps. Only one attempt is made; errors do not imply an operation is safe to
retry. Responses retain only selected fields, never arbitrary provider metadata or
hidden reasoning. Refusal text is discarded. Missing usage remains null.

| Condition                                                                   | Error code / outcome                                             |
| --------------------------------------------------------------------------- | ---------------------------------------------------------------- |
| HTTP 401/403                                                                | `provider_authentication`                                        |
| HTTP 429                                                                    | `provider_rate_limited`                                          |
| HTTP 408/504 or elapsed deadline/HTTPX timeout                              | `provider_timeout`                                               |
| Other HTTP 5xx or connection/transport failure                              | `provider_unavailable`                                           |
| Other non-2xx, including redirects; oversized/invalid encoded request       | `provider_rejected`                                              |
| Bad response JSON/envelope, native calls, body overflow or decoding failure | `invalid_response`                                               |
| Provider refusal/content filtering                                          | Response reason `refusal`, unusable by action validator          |
| Output limit / unknown finish reason                                        | Response reason `length` / `other`, unusable by action validator |

Keep the provider call and action validation outside database transactions. Commit
intent first, then persist the selected outcome with revision/event-position checks.
No automatic persistence, run transitions, retries or tools are added to providers.

Offline adapter checks use HTTPX mock transports, including stalled streamed bodies:

```sh
uv run pytest packages/model_providers/tests
```

## Opt-in live verification

The ordinary test suite and CI never contact a model provider. This separate command
makes exactly one potentially billable fixture request with a 256-token completion
limit and 30-second deadline. It requires an explicitly selected compatible model:

```sh
export RUNVEIL_PROVIDER_MODEL='your-compatible-model-id'
export RUNVEIL_PROVIDER_BASE_URL='https://api.openai.com/v1'
# Set RUNVEIL_PROVIDER_API_KEY securely in the shell environment; do not paste it
# into source, command history or handoff output. Python does not auto-load .env.
uv run python -m runveil_providers.live --live
```

Omitting `--live` exits before configuration or client creation. Missing/invalid
configuration fails before dispatch. The command validates a finish action with
no artifacts and prints only success, normalized usage and latency. Failure prints
a fixed code, never raw HTTP bodies, response content, credentials or exception
text. Exit codes: 0 passed, 1 provider/action failure, 2 opt-in/configuration/fixture
failure, 130 interrupted. No output file or database record is created.

The Phase 2 manual hosted acceptance gate is complete. The user reported a successful
invocation against the configured OpenAI-compatible endpoint; see the
[safe acceptance evidence](PHASE_2B.md#subsequent-hosted-live-acceptance--complete).
Future live checks remain explicitly opt-in. See the [roadmap](../../ROADMAP.md)
for current implementation and review status.
