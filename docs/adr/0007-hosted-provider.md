# ADR 0007: Bounded OpenAI-compatible Chat Completions adapter

- Status: Accepted for Phase 2B
- Date: 2026-09-26

## Decision

Add `runveil_providers` in a real uv workspace package. It owns HTTPX transport,
configuration and wire normalization, depending on the core contracts, never the
reverse. One `OpenAICompatibleProvider` targets OpenAI by default or an explicitly
configured compatible base URL. Use HTTPX directly for this single non-streaming
endpoint rather than adding a vendor SDK, implicit SDK retries or a second hosted
wrapper class. The provider owns its async client; callers close it with an async
context manager. A transport injection point supports offline tests.

Send one POST to `chat/completions` with JSON mode, temperature and
`max_completion_tokens`. Add a system message describing the fixed action schema
and advertised tools. Preserve text message order. Core tool-result messages have
no native call IDs, so encode them as labelled, untrusted JSON observations in user
messages. Never invent native call IDs or execute tools. Native tool calls in a
response are rejected. No streaming, Responses API, model routing, automatic
capability discovery, fallback, output repair or retries are added.

The Phase 2A schema uses a union at the root and arbitrary JSON-object arguments.
OpenAI strict Structured Outputs requires a root object and closed objects; blindly
submitting that schema would be incorrect. JSON mode is an explicit supported
profile, not a silent downgrade. Runveil's `validate_response` remains the authority
for action shape and advertised names; callers must invoke it after generation.
Unsupported endpoint/model settings fail as `provider_rejected`. This adapter only
claims compatibility with servers supporting this documented request profile.

## Boundaries

Configuration is operator-supplied, separate from persisted requests. Keys use
`SecretStr`; neither the adapter nor the live command logs payloads, keys, raw
exceptions or provider error bodies. HTTPS is required except literal loopback
addresses/localhost for local development. Reject URL credentials, query and
fragment. Disable redirects and environment proxy/netrc inheritance; never move a
credential to a redirect destination. This is not a public user-configurable URL
fetcher or an SSRF sandbox. DNS/egress policy belongs to later deployment work.

Limit encoded request and decoded response bodies to 2 MiB. Bound the network
operation with a whole-call asyncio deadline plus HTTPX timeouts. Cancellation
propagates unchanged. Timeout maps to `provider_timeout`; connection failures to
`provider_unavailable`; 401/403 to authentication; 429 to rate-limited; 408/504 to
timeout; remaining 5xx to unavailable; other non-2xx responses to rejected.
Codes express observations, not safe-to-retry guarantees. Reject malformed wire
JSON/envelopes as `invalid_response`, without raw diagnostic text.

Normalize exactly one assistant choice. Discard raw provider extras/reasoning,
retain only model/content/finish reason/usage/request ID, and measure monotonic
latency including response reading. Refusal/content filtering maps to `refusal`
without retaining refusal text; length/unknown finish reasons remain unusable by
the core action validator. Missing token counts remain null. Resolved model IDs
may differ from requested aliases. Usage is provider-reported, not billing proof.

## Verification and consequences

Offline tests exercise the same runtime-facing action contract with scripted and
HTTP-backed providers, inspect the outbound wire request, and cover failures,
limits, redirects, timeout, cancellation and client cleanup. No database or runtime
changes are required; Phase 2A already verifies persistence serialization.

A separate `python -m runveil_providers.live` command requires an explicit `--live`
flag plus endpoint, model and key configuration as appropriate. It makes one small
fixture request, validates a finish action and prints only success/usage/latency or
a fixed error code. CI never invokes it. Without an authorized configured live
run, the hosted manual acceptance gate remains outstanding even when offline
implementation checks pass. Phase 3 is the next implementation slice after review.

Sources checked 2026-09-26:
[structured outputs and JSON mode](https://developers.openai.com/api/docs/guides/structured-outputs)
and [Chat Completions parameters](https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create).
