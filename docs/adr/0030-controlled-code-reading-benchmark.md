# ADR 0030: Controlled code-reading benchmark and split discipline

- Status: Accepted for Phase 8B
- Date: 2026-10-01

## Decision

Expand the Phase 8 foundation with a separately named/versioned 24-case Python
code-reading corpus: 16 development cases and 8 held-out cases. Preserve the
three-case calibration suite and its default CLI behavior. Select the larger
benchmark with `--suite code-reading`; development is the default split and
`--split held-out` is explicit. Reject unsupported suite/split combinations before
creating output or database state. There is no combined score across splits.

Every task has a small public source fixture, unambiguous exact answer and an
explicit read or search-then-read requirement. Cover defaults, branches, collections,
strings, iteration, exceptions, scope and source inspection. Human-reviewed answer
rationales accompany the inventory. Source fixtures are data; never import, eval,
exec or launch them. Reuse the existing frozen contracts, exact scorer, read-tool
allowlist, claimed execution, immutable three/five-step configurations and local
comparison report. No new provider, mutation, policy, grader plugin or schema table.

Split is part of the canonical suite digest. Each report embeds only its selected
partition and its complete case denominator; comparison refuses different partitions
as it refuses any different suite content. Freeze v1 membership/content before
acceptance; substantive changes require a benchmark version bump and fresh evidence.
Stable digests guard against accidental drift. Do not update historical reports.

## Evidence and limitations

Both partitions are shipped publicly, with scripts containing answers. Held-out
means reserved from prompt/provider tuning, not confidential or contamination-proof.
Offline CI execution checks harness plumbing on both partitions and does not create
model-generalization evidence. Development is for future iteration; inspect held-out
model results only after fixing configurations, and record exposure before tuning.
If tuning uses those results, retire their held-out claim and create fresh cases for
future claims. No held-out model evaluation has happened in this slice.

The benchmark covers 24 controlled code-reading tasks, not code repair, generated
test execution or a sandboxed coding agent. Three/five-step differences are deliberately
constructed budget effects; scripted grades validate wiring/oracles, not inference
quality. Synthetic usage/pricing and variable timing retain Phase 8A meanings.
Existing failure/authorization tests remain the security evidence; a larger set of
successful scripts is not a replacement for them. Full Phase 8 closure needs a
separate acceptance/scope audit; Phase 9 statistics and Phase 10 sandbox remain later.
