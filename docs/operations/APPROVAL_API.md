# Local operator approval HTTP API

Phase 6D adds inspection and decisions for already-created Phase 6A, 6B and 6C
approvals. See [ADR 0024](../adr/0024-local-operator-approval-api.md).
The [review](APPROVALS.md) and [patch](PATCHES.md) CLIs still create and run work.
The console is not connected yet.

## Enable locally

Use the database setup in [development](DEVELOPMENT.md), then generate a fresh
secret in the API terminal without printing it:

```sh
export RUNVEIL_APPROVAL_TOKEN="$(uv run python -c 'import secrets; print(secrets.token_urlsafe(32))')"
uv run uvicorn runveil_api.main:app --host 127.0.0.1 --port 8000
```

The value must be a randomly generated 43–128 character URL-safe token. Missing or
invalid configuration returns `503 approvals_disabled`; liveness/readiness remain
independent. Restart to rotate or disable it. Keep it out of source, shell history,
request logs, traces and `.env` files. This shared capability permits inspection
and decisions on every supported approval in the configured database. It provides
no per-user attribution or per-run access restriction. Use loopback only; a public
or shared deployment needs its own authentication/deployment review and TLS.

## Inspect, then decide

Send the secret only as `Authorization: Bearer <token>`. Do not put it in a URL,
cookie or proposal. For example, a local HTTP client can read it from its process
environment without putting its value in command-line arguments. Disable body and
authorization-header logging in clients and proxies.

`GET /approvals/{run_id}` returns:

- `request`: approval ID, run ID, exact `proposal` (`path`, `before`, `after`,
  schema version), SHA-256 `digest`, status and decision timestamps.
- `profile`, `run_status`, `run_revision`.
- `workspace`: pinned root/content/implementation fingerprints, or null for the
  standalone review workflow. These are identities, not current filesystem checks.
- `mutation`: null before mutation intent, otherwise its `status` and `error_code`.
  A requested or uncertain/failed mutation does not prove the file is unchanged.

After inspecting the complete proposal and profile, send
`POST /approvals/{run_id}/decision` with `Content-Type: application/json` and:

```json
{
  "decision": "APPROVED",
  "expected_profile": "repository-patch-v1",
  "expected_approval_id": "<request.id from inspection>",
  "expected_revision": 2,
  "expected_digest": "<request.digest from inspection>"
}
```

Use the exact inspected revision, not the example number. Use `REJECTED` to deny.
Unknown fields, including write grants or replacement proposal text, are refused.
The successful response has the same inspection shape and reflects the committed
decision. Competing/duplicate decisions do not silently succeed.

| Profile                | Approval consequence                                                                                                                         |
| ---------------------- | -------------------------------------------------------------------------------------------------------------------------------------------- |
| `patch-review-v1`      | Completes the standalone review; no file write                                                                                               |
| `repository-review-v1` | Makes review worker continuation eligible; no file write                                                                                     |
| `repository-patch-v1`  | Makes patch continuation eligible; later worker still requires separate `--allow-write`, matching workspace and all existing mutation checks |

Rejection terminates the pending workflow. The API never executes a worker. For
worker profiles the original deadline continues across approval waiting. An
approved run can still fail due to expired budgets, changed workspace or denied
execution permissions.

## Failure handling

All handled responses are non-cacheable and expose fixed errors:

| Status | Meaning                                                                                             |
| ------ | --------------------------------------------------------------------------------------------------- |
| 401    | Missing, duplicated or invalid bearer credential                                                    |
| 404    | Run/approval absent                                                                                 |
| 409    | Stale decision, unsupported/inconsistent profile or invalid approval state; inspect before deciding |
| 413    | Decision body exceeds 2 KiB                                                                         |
| 415    | JSON content type required                                                                          |
| 422    | Invalid UUID or strict decision payload                                                             |
| 503    | Approval surface disabled, database unavailable or five-second request timeout                      |

After a lost response or 503, GET the approval again. Never infer rollback from a
transport failure or retry approval blindly. Database decisions remain atomic;
client acknowledgement is not atomic with commit. Authentication is checked before
input/database handling, so unauthenticated callers cannot inspect existence.
There is no listing, submission, grant, worker-start or cancellation endpoint.
