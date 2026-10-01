# Phase 2B handoff

Date: 2026-09-26. Implementation complete and stopped for review. The manual hosted
acceptance gate is complete; see the subsequent user-reported evidence below.
No commit or push.

## Implementation summary

Inspected the clean repository, AGENTS instructions, charter, architecture, roadmap,
accepted decisions, Phase 2A contracts/scripted provider/tests, persistence boundary
and prior handoff, README and CI. Used official OpenAI documentation to verify the
wire profile and JSON/strict-schema distinction. Recorded ADR 0007 before coding.

Added the `runveil-model-providers` uv package with an OpenAI-compatible hosted
adapter, validated operator configuration and an explicitly opt-in live command.
The adapter uses HTTPX directly for one bounded non-streaming Chat Completions
request. It normalizes selected response fields, nullable usage and measured
latency, maps failures to safe codes, propagates cancellation and closes streams.
There are no implicit retries or provider calls in ordinary tests/CI.

Six focused offline test functions (15 parametrized cases) exercise the shared
runtime-facing contract, outbound message/settings mapping, normalization and bad
responses, error safety, redirects, size limits, deadline/cancellation cleanup and
live-command guard/success/failure paths through injected offline transport.
The workspace and test discovery include the new package. Lockfile changes add
only the new package/dependency edges; no existing dependency version changed.
No runtime loop, migrations, persistence changes, tool execution, web changes or
application HTTP routes were introduced.

## Decisions and boundaries

See [ADR 0007](../adr/0007-hosted-provider.md) and [provider operations](MODELS.md).

- Keep HTTP concerns in a separate adapter package, with dependency direction
  toward `runveil_core`. One configurable adapter covers the default OpenAI endpoint
  and compatible services; no redundant hosted wrapper or generic adapter framework.
- Explicitly use JSON mode plus the existing action validator. Phase 2A's root
  union/open-ended arguments cannot be sent unchanged as OpenAI strict Structured
  Outputs. No silent schema/parameter fallback, native tool calls or output repair.
- Serialize tool observations as labelled untrusted JSON data in user messages;
  core messages lack native call IDs. This is context formatting, not authorization.
- Keep secrets outside invocation payloads. Require HTTPS remotely, disable
  redirects and environment proxy/netrc inheritance, and use `SecretStr` for keys.
  Endpoint configuration is trusted operator input, not a public URL-fetch API.
- Bound outgoing and incoming bodies to 2 MiB and apply an asyncio network deadline
  plus HTTPX timeouts. Preserve caller cancellation. Error codes are not retry advice.
- Retain only normalized response fields. Refusal text and arbitrary vendor extras
  are discarded. Callers still validate actions before use or successful persistence.
- Keep manual live verification separate from CI, behind `--live` and explicit model
  and credential configuration. Do not infer paid-call opt-in from a normal test run.

## Verification commands and results

Environment: macOS, Python 3.12.14, uv 0.12.19, Node 24.19.0 selected explicitly,
Docker PostgreSQL. Only a task-owned Compose project was used:

```sh
export PATH="$HOME/.nvm/versions/node/v24.19.0/bin:$PATH"
POSTGRES_USER=runveil POSTGRES_PASSWORD=runveil-local-only POSTGRES_DB=runveil POSTGRES_PORT=55432 docker compose -p runveil-phase2b up -d --wait --wait-timeout 90
export DATABASE_URL='postgresql+psycopg://runveil:runveil-local-only@127.0.0.1:55432/runveil'
export RUNVEIL_TEST_DATABASE_URL='postgresql+psycopg://runveil:runveil-local-only@127.0.0.1:55432/postgres'
```

| Command                                                                     | Result                                                        |
| --------------------------------------------------------------------------- | ------------------------------------------------------------- |
| `uv lock`                                                                   | Added new workspace package; no dependency version changes    |
| `uv sync --locked --all-packages`                                           | Passed                                                        |
| `uv run ruff format --check .`                                              | Passed                                                        |
| `uv run ruff check .`                                                       | Passed                                                        |
| `uv run mypy`                                                               | Passed; 38 source files                                       |
| `uv run pytest -m 'not integration'`                                        | 102 passed; 22 integration tests deselected                   |
| `uv run pytest -m integration`                                              | 22 passed; 102 other tests deselected; no skips               |
| `uv run pytest packages/model_providers/tests`                              | 15 passed, including final added CLI/finish-reason assertions |
| `uv run alembic upgrade head`                                               | Passed on empty task database                                 |
| `uv run alembic check`                                                      | No new upgrade operations detected                            |
| `docker compose -p runveil-phase2b config --quiet` with the variables above | Passed                                                        |
| `npm ci`                                                                    | Passed; zero audit vulnerabilities                            |
| `npm run format:check`                                                      | Passed                                                        |
| `npm run lint`                                                              | Passed                                                        |
| `npm run typecheck`                                                         | Passed                                                        |
| `npm test`                                                                  | One web test passed                                           |
| `npm run build`                                                             | Production build passed                                       |
| `uv run python scripts/smoke.py` with database URL                          | API/web liveness, production page and readiness 200 passed    |
| `env -u DATABASE_URL uv run python scripts/smoke.py`                        | API/web liveness, production page and readiness 503 passed    |
| `uv run python -m runveil_providers.live --help`                            | Installed module/CLI help passed without network              |
| `git diff --check`                                                          | Passed                                                        |

Initial Ruff checks caught a loop-variable capture in a test callback; explicitly
bound it before final checks. Review also allowed empty native-tool arrays (no call)
while rejecting actual native calls, mapped decoding failures separately, and added
safe request-serialization rejection. The new package was verified through the
locked editable workspace installation. No hosted CI execution or real provider
invocation was run during the implementation checks; subsequent hosted evidence
is recorded below. CI's existing checks discover the new tests through the updated
root testpaths. npm reported existing ESLint deprecation/install-script notices and
an npm update notice; no frontend dependency changes were made.

Confirmed zero remaining `runveil_test_*` databases. Removed only the task-created
`runveil-phase2b` container, network and volume with the same Compose variables and
`docker compose -p runveil-phase2b down --volumes`. Existing services, volumes and
local `.env` were preserved. Smoke processes stopped themselves.

## Subsequent hosted live acceptance — complete

The user reported a successful Phase 2 hosted live acceptance against the configured
OpenAI-compatible endpoint. Safe evidence supplied:

| Field         | Result     |
| ------------- | ---------- |
| Status        | `passed`   |
| Action        | `finish`   |
| Input tokens  | 524        |
| Output tokens | 16         |
| Latency       | 2211.37 ms |

This closes the Phase 2 manual hosted acceptance gate. This documentation update
records user-supplied evidence; it did not rerun the live request. No endpoint URL,
model/account identifiers, credentials, request content or raw response is recorded.
The result establishes acceptance for that configured invocation, not universal
provider compatibility or a performance benchmark.

## Files created

- `docs/adr/0007-hosted-provider.md`
- `docs/operations/PHASE_2B.md`
- `packages/model_providers/pyproject.toml`
- `packages/model_providers/src/runveil_providers/__init__.py`
- `packages/model_providers/src/runveil_providers/py.typed`
- `packages/model_providers/src/runveil_providers/configuration.py`
- `packages/model_providers/src/runveil_providers/chat.py`
- `packages/model_providers/src/runveil_providers/live.py`
- `packages/model_providers/tests/test_chat.py`

## Files modified

- `ARCHITECTURE.md`
- `README.md`
- `ROADMAP.md`
- `docs/operations/MODELS.md`
- `packages/agent_core/src/runveil_core/models.py` (adds `provider_rejected`)
- `pyproject.toml`
- `uv.lock`

## Remaining concerns and next slice

The manual hosted acceptance gate is **complete**, based on the subsequent
user-reported result above. Future live checks remain explicitly opt-in.

Compatibility is limited to the documented Chat Completions JSON-mode profile,
including temperature and max-completion-token support. Models requiring different
parameters, Responses API or strict server-enforced action schemas need a deliberate
future adapter/profile. JSON mode alone does not validate action semantics.

Limits bound accumulated bodies, not all serialization/decompression memory or
CPU time. Cancellation/timeout cannot establish whether a remote request completed
or was billed. The adapter never retries. Deployment egress/DNS policy, key rotation,
provider-specific accounting, routing, tracing and stronger tool schema/policy work
remain later concerns. No caller should store secrets or hidden reasoning; selected
content remains the caller's responsibility.

At the original handoff, the recommended next implementation was **Phase 3**
(now implemented; see the [current roadmap](../../ROADMAP.md)):
a minimal persisted scripted model → trivial read-only tool → model → finish loop,
with a maximum step bound and checkpoints. Worker leases, replay/recovery, retries
and general tool authorization stay in their planned phases. Stop for review here.
