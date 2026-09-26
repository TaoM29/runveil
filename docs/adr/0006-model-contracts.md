# ADR 0006: Normalized model contracts and scripted responses

- Status: Accepted for Phase 2A
- Date: 2026-09-26

## Decision and scope

Implement the first planned Phase 2 review slice in `runveil_core`: validated
request/response contracts, a provider protocol, structured actions and an offline
scripted provider. Pydantic is a supporting validation dependency; the runtime
remains project-owned. A separate adapter package becomes useful when Phase 2B
adds real HTTP/provider behavior. No runtime, dispatch, retries or schema migration
is introduced here.

`ModelProvider.generate` is async and returns a normalized response envelope.
Requests carry ordered text messages, model, tool descriptions/input schemas,
temperature, output-token limit and timeout. The fixed version-1 action schema is
available from `action_schema()`; arbitrary response-schema negotiation is deferred.
Responses carry content, a normalized finish reason, nullable token counts,
latency and an optional provider request ID. Missing usage is unknown, never zero.
No raw provider payload, credentials, transport configuration or reasoning field
belongs in these contracts. Adapters will measure latency and enforce the timeout;
the scripted provider returns fixture timing without sleeping.

Actions are exactly one `tool_call` or `finish`. Tool actions contain a name,
JSON-object arguments and a concise decision summary; finish actions contain a
summary and artifact references (strings, never fetched or executed). Parsing
rejects extra fields, malformed/duplicate-key/non-finite JSON, oversized content,
wrong types and incomplete/refused responses. A tool name must be advertised in
the request. This is structural validation only: tool argument-schema validation,
authorization, approval and execution remain Phase 4 responsibilities. Advertised
input schemas are JSON objects, not yet a supported/validated JSON Schema dialect.

Transport failures use fixed error codes and generic messages. Invalid model
content is converted to `invalid_response` without including the raw content or
validation details. These are not retry directives. Cancellation must propagate;
a future adapter must not convert it into a normal provider failure. No automatic
repair of model output or implicit retry is permitted by this contract.

Pydantic contract objects freeze field assignment. JSON dictionaries remain
caller-owned mutable values; they are not the deeply immutable Phase 1 domain
snapshots. The scripted provider serializes its script at construction and request
history at call time, and returns freshly validated copies. Neither caller mutation
nor inspecting request history can change its retained fixtures/history. One
script belongs to one ordered consumer; sharing it across concurrent runs makes
assignment depend on call order and is unsupported for reproducible tests.

## Persistence and trade-offs

Versioned contract JSON fits the existing opaque invocation request/result fields.
`model_dump(mode="json")` provides detached JSON objects; `model_validate_json` restores
them. No existing record is reinterpreted or migrated. A future runtime must commit
intent, call the provider outside the transaction, validate the response, then
persist a selected outcome using revision/sequence checks. The integration test
exercises those boundaries without implementing the loop.

A single JSON action envelope avoids separate competing text/native-tool action
paths in the first slice. Hosted adapters may normalize native provider output to
this envelope later. Fixed contracts are intentionally narrower than every vendor
API. SDK error mapping, capabilities, live verification and actual timeout handling
remain Phase 2B review work. Persistence is still not a redaction service: callers
must select safe message/output content before storage.
