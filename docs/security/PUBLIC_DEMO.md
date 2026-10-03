# Public-demo safety model

Phase 15C local policy, 2026-10-03. This defines what may be demonstrated; it does
not authorize hosting or claim that a public deployment exists. Phase 12C remains
paused. Read alongside the [threat model](THREAT_MODEL.md) and
[recorded showcase runbook](../operations/SHOWCASE.md).

## Audience and authority

| Actor                                                      | May do                                                                                                                                                                                             | May not do                                                                                                                                                                                                                 |
| ---------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Anonymous visitor to a future reviewed public presentation | Inspect seeded example runs, selected trace evidence, patches/test observations, benchmark reports and architecture; search/filter the recorded archive.                                           | Query private live runs, upload a repository, supply a task/prompt/model/URL, start execution, invoke tools, approve/reject changes, provide credentials or change policy.                                                 |
| Viewer of the current local showcase                       | Inspect `/`, `/runs` and exact retained `/runs/[runId]` records without credentials.                                                                                                               | Gain authority from a record, a run ID, browser controls or text inside a fixture.                                                                                                                                         |
| Trusted local operator                                     | Use separate trace/approval credentials for supported local API profiles; initiate reviewed project-owned fixture workflows from the CLI with explicit grants and bounded immutable configuration. | Treat a trace credential as approval authority, treat prior approval as permission for another proposal/profile, broaden fixture execution to unreviewed repositories or expose local operator routes as a public service. |

Anonymous/public execution allowance is **zero**. Public model usage and public
execution budgets are therefore zero. There is no repository upload, generic shell,
network-fetch, model-selection or run-submission endpoint to enable in this slice.
Existing local operator bearer tokens are not a production authentication design.

## Read-only evidence

The showcase explicitly imports the Phase 10G task artifact and Phase 10F
failed-validation artifact through `apps/web/lib/showcase.ts`. It projects selected
fields rather than enumerating files or querying the database. Runs are labelled
recorded, scripted fixture evidence, including the deliberately failed validation.
Untrusted source, diffs and output render as text. No model-quality, current live
activity or real billing claim follows from synthetic fixture results.

Review every newly selected artifact for credentials, private paths, source and
personal data before adding it to the archive. The finite telemetry metadata policy
does not redact arbitrary durable payloads or make raw database dumps public-safe.
The authenticated live trace API and the static archive are separate disclosures.

The current web application still contains local operator pages and loopback-only
proxies. Do not publish the whole development stack or share an operator bearer
token as a demo shortcut. Host/origin checks limit browser misuse; they are not a
substitute for authentication or deployment network controls.

## Controlled local execution

Use only the three project-owned coding fixtures in the fixed task catalog with a
reviewed local immutable Docker image. The CLI operator selects the fixed task,
not a visitor-supplied checkout, executable, test command, endpoint or model. Normal
demonstrations use the existing scripted provider and consume no paid API calls.
Live hosted-model tests remain separately opt-in and outside this demo policy.

Keep explicit READ/EXECUTE and, for the exact approved mutation, WRITE grants.
Approval binds the inspected proposal, profile, revision and workspace identity.
Retain every profile's pinned limits; do not remove limits to keep a demo running.
For the search-enabled coding workflow, current configuration permits at most nine
steps, four model calls and five tool calls, with the inherited one-hour elapsed
deadline (including approval waiting), token and repetition caps. Its 125,000
nano-USD cap uses synthetic fixture pricing, not real-provider billing guarantees.

The Docker runner retains no network, host checkout mounts or daemon socket mount;
non-root execution, dropped capabilities, read-only root and bounded tmpfs;
0.5 CPU, 128 MiB memory with no extra swap, 32 PIDs, bounded output and fixed test
watchdogs. Proposed code executes only in that disposable fixture environment.
Test success is an observation, not proof of harmlessness or sandbox-escape safety.
See [sandbox operations](../operations/SANDBOX.md) for exact commands and limits.

For demonstrations, the operator starts one workflow at a time and inspects its
outcome and confirmed cleanup before another. This is an operational rule, not a
new global concurrency lock. Existing run limits do not enforce aggregate quotas.
On uncertain mutation or cleanup, stop, inspect durable intent/container identity
and follow the runbook. Never replay an uncertain effect to make the demo appear
successful, or claim a failed run implies that no effect occurred.

## Later public-deployment gates

Before any public execution is reconsidered, complete Phase 12C live acceptance,
Phase 13 delivery and Phase 14 inference work, then review the remaining Phase 15
controls: appropriate administrative authentication/authorization, aggregate
admission/rate/concurrency/cost caps, network egress and destination controls,
cloud IAM and secrets, public/private route separation, abuse monitoring, retention
and cleanup operations, and evidence of isolation for the proposed exposure.
Keep arbitrary repositories and unrestricted shell/network access prohibited.
Phase 16 release remains gated on those reviews.

## Local evidence

No new runtime mode, API route or tool is necessary: current archive imports,
absence of submission APIs, default-deny local authorization and fixture CLI
boundaries implement the allowed local behavior. Existing API authentication,
approval/trace proxy, showcase, sandbox, budget and durable-effect tests exercise
these controls. This policy is not a claim of aggregate rate limiting or a public
penetration test. Current commands/results and gaps are in the
[Phase 15 handoff](../operations/PHASE_15.md).
