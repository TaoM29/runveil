# ADR 0015: Pinned pricing and durable cost budgets

- Status: Accepted for Phase 5E
- Date: 2026-09-29

## Decision

Configuration/checkpoint version 6 adds a required USD price snapshot and positive
`max_cost_nanousd`, alongside the existing elapsed/token limits. Snapshot fields
are `price_id`, `provider`, `model`, `currency` (USD), and integer
`input_nanousd_per_token` / `output_nanousd_per_token`. One nano-USD is 10^-9 USD.
Rates are nonnegative integers up to 10^9; the run limit is at most 10^15 nano-USD.
No floats, rounding, exchange rates or mutable price lookup participate.

Pricing applies to the configured request model/binding, including aliases, and
must match the pinned provider/model. Missing rates, unsupported currency or
mismatched identity reject configuration before execution. Zero rates must be
explicit. A price ID identifies the snapshot for audit; the full immutable rates
are authoritative. Only linear input/output pricing is supported. Operators must
not use it to represent cache tiers, reasoning-token surcharges, request fees or
other billing schemes that the normalized usage contract cannot express.

Version-6 checkpoints persist `cost.known_nanousd` and `cost.unknown_attempts`.
Cost is derived exactly from cumulative known token components and pinned rates.
This retains known partial cost while distinguishing unknown consumption from
zero, even at zero rates. Invalid actions and known failed attempts still count;
retries/restarts never reset totals. Recompute cost from pinned rates on recovery
and validate it at outcome boundaries. No migration or additional ledger is needed.

Reaching a cost limit fails as `cost_limit_exceeded` with `budget.exceeded` before
accepting the model action or scheduling a retry. Token unknown/limit failures
retain precedence; their checkpoint still records cost. Interrupted intent and
elapsed expiry preserve the existing error precedence and account uncertain
model usage. All history, accounting and terminal writes share the existing
ownership-fenced transaction. Older profiles retain their behavior.

## Limits and next boundaries

This is a reproducible estimate under a pinned linear tariff, not an invoice or
hard spending cap. A call can overshoot a post-attempt threshold. Invalid pricing
never silently becomes free execution; no current provider pricing is fetched.
The new `fixture-cost-v1` uses synthetic rates and usage only. Hosted replay,
price discovery, richer billing dimensions and external side-effect idempotency
remain separate work. The next coherent reliability slice is bounded repeated
action detection using durable history, before expanding execution capabilities.
