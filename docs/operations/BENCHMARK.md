# Controlled code-reading benchmark v1

Phase 8B adds **24 distinct Python code-reading tasks**: 16 development and 8
held-out. The corpus is authored in
[`benchmark.py`](../../packages/evaluations/src/runveil_evaluations/benchmark.py).
Each case owns a task, bounded public `example.py`, scripted actions, exact answer
and ordered tool-name oracle. Every task requires reading the source; half also
require searching for one uniquely occurring definition first. No source is executed.

This is a controlled **scripted benchmark of the evaluation harness**. Scripts
contain answers, so passing is not evidence of reasoning, code repair, regression
safety or model quality. Exact tool-name checks establish the declared call sequence,
not that a model understood a tool result. There is no sandbox or test runner.
The original three-case `calibration` suite is preserved separately.

## Frozen inventory and answer review

`R` means one read then finish (three runtime steps); `SR` means search, read,
then finish (five steps). Answers are exact strings with no quote characters or
normalization. Tasks specify the requested output and supplied input. Rationales
below were reviewed from the source without importing or running fixture code.
These are semantic spot explanations, not a claim of an independent executable oracle.

| Development case         | Path | Answer        | Source rationale                                                        |
| ------------------------ | ---- | ------------- | ----------------------------------------------------------------------- |
| defaults-retries         | R    | `3`           | The retries parameter has literal default 3.                            |
| defaults-keyword-only    | SR   | `False`       | compact is keyword-only with default False.                             |
| branches-inclusive       | R    | `low`         | The `<= 5` condition includes input 5.                                  |
| branches-first-match     | SR   | `negative`    | The negative branch returns before parity is checked.                   |
| collections-copy         | R    | `2`           | Appending to a slice copy does not extend the original.                 |
| collections-fallback     | SR   | `9`           | The absent key selects the explicit get fallback.                       |
| strings-normalize        | R    | `a`           | Stripping the spaces then lowercasing A produces a.                     |
| strings-split-limit      | SR   | `b:c`         | One split leaves the second colon in the tail.                          |
| iteration-range          | R    | `9`           | range(1, 6, 2) contributes 1, 3 and 5.                                  |
| iteration-filter         | SR   | `3`           | The even values in range(6) are 0, 2 and 4.                             |
| exceptions-fallback      | R    | `-1`          | Invalid integer text takes the ValueError handler.                      |
| exceptions-finally       | SR   | `try,finally` | Both append operations run in that order before the join.               |
| scope-shadowing          | R    | `2`           | The function returns its local LIMIT.                                   |
| scope-closure            | SR   | `pre-x`       | label retains the prefix supplied to build.                             |
| inspection-async         | R    | `read`        | The awaited expression invokes reader.read.                             |
| inspection-resource-mode | SR   | `r`           | open receives the explicit mode r; no file is opened during evaluation. |

| Held-out case           | Path | Answer     | Source rationale                                                        |
| ----------------------- | ---- | ---------- | ----------------------------------------------------------------------- |
| defaults-captured-value | R    | `4`        | The default captures LIMIT at definition time, before its reassignment. |
| branches-short-circuit  | SR   | `False`    | The empty-list guard short-circuits before indexing.                    |
| collections-alias       | R    | `7`        | alias and values reference the same list.                               |
| strings-suffix          | SR   | `copy.py`  | removesuffix removes only the final .py.                                |
| iteration-zip-bound     | R    | `2`        | zip stops at the shorter input.                                         |
| exceptions-else         | SR   | `ok`       | Successful int conversion takes the try/else branch.                    |
| scope-nonlocal          | R    | `3`        | bump updates the enclosing value from 1 to 3.                           |
| inspection-handler-type | SR   | `KeyError` | The exception handler names KeyError.                                   |

Both partitions cover all eight subject areas. IDs, full source strings and tasks
are disjoint. They share concepts intentionally: this is a task partition, not a
held-out domain or distribution-shift experiment. Static verification checks syntax,
bounded content, unique search locations, read-only script shape and frozen digests.
Database acceptance runs all 24 cases through both configurations in one integration
test, keeping failed cases in the denominator. Existing negative-oracle and
permission/path tests continue to establish failure boundaries.

## Version and split discipline

The benchmark name is `controlled-code-reading`, version `1`. Canonical digests
include schema/scorer version, split, ordered case membership, tasks, source,
scripts and oracles:

- Development: `b1992916d46a1f5d7b5748069f5de387166a4a4a3aa184fae23e7d0fe997de49`
- Held-out: `6a95d546f370e70b0b1bb128a91d66ff5f7b88ef9d2388d07a84b45465fe481f`

Freeze these before acceptance. Changing content or membership requires a version
bump, review of the rationale, new digests and new evidence; never replace an old
report to make it agree with a changed benchmark. Python formatting changes that
leave the serialized suite unchanged do not change these content digests, but may
change the separate implementation fingerprint.

The CLI defaults to development and requires explicit `--split held-out` selection.
Each comparison includes exactly one partition. Never pool the two rates or compare
a development baseline to a held-out candidate. Both immutable configurations
within a report use the exact same ordered tasks and scripts. The held-out label
is part of identity; relabeling unchanged cases also invalidates comparison.

**Held-out is a usage rule, not a confidentiality boundary.** The cases and answers
are public and the evaluator author has reviewed them. They are not a contamination-
free challenge for this assistant or any model that has encountered the repository.
Use development cases for future prompt/provider tuning. Fix configurations before
examining held-out provider results, and record that exposure in the evaluation
handoff. If such results inform tuning, retire the held-out claim for that iteration
and create fresh cases for subsequent generalization claims. CLI selection cannot
enforce this human process or prevent someone importing the module directly.

This slice freezes the public partition and exercises it only through scripted
plumbing checks. CI may repeat those checks: no prompts, providers or budgets are
optimized from held-out outcomes. No actual held-out model evaluation is claimed.

## Reproduce and interpret

Follow [evaluation operations](EVALUATIONS.md) with a migrated local database:

```sh
uv run python -m runveil_evaluations --suite code-reading --output /tmp/code-reading-development.json
uv run python -m runveil_evaluations --suite code-reading --split held-out --output /tmp/code-reading-held-out.json
```

Development should score **8/16 → 16/16**, held-out **4/8 → 8/8**. Each three-step
baseline fails only the search/read tasks at `step_limit_exceeded`. Search-then-read
candidates finish exactly at the five-step budget; single-read cases consume three
steps under either configuration. These rates are deliberately
constructed budget effects, not model improvement estimates. Synthetic token/cost
accounting retains the Phase 8A labels; wall-clock timing is not reproducible.

See [ADR 0030](../adr/0030-controlled-code-reading-benchmark.md) and the
[Phase 8B handoff](PHASE_8B.md) for verification and retained reports. The
[Phase 8 closure audit](PHASE_8.md) accepts this scripted scope; code repair/test
execution and statistical inference have not been brought forward from later phases.
