# Public-readiness review

Reviewed 2026-09-29 against commit `5327e761f01411d3fbf651100c918756c40c46d4`
and the uncommitted presentation/privacy fixes described below. The repository
was private at review time. Phase 5 is complete; this review adds no Phase 6 work.

## Recommendation: not ready yet

Resolve these owner decisions before changing visibility:

- **License:** no license file or GitHub-detected license exists. Select the
  intended license and add its text and ownership information. Alternatively,
  explicitly decide to publish without a license grant and document that choice.
  Public visibility alone does not supply the missing license grant.
- **Public name:** [the naming record](../architecture/NAMING.md) explicitly
  leaves Runveil unapproved for publication. Complete that decision and update
  the working-name notice; the earlier collision research covers former names.
- **History privacy:** eleven historical handoffs expose a local username/path;
  one also exposes a local attachment identifier and filename. Current copies
  are sanitized, but earlier commits retain them. Decide whether that disclosure
  is acceptable or arrange a separately authorized history cleanup before
  publication. No history rewrite was performed. These are privacy details,
  not evidence of exposed credentials.

After resolving these decisions, review and commit the fixes separately, obtain
CI on that commit, and recheck the final publication refs. Do not begin Phase 6
as part of publication preparation.

## Evidence and scope

- Inspected tracked files, ignore rules, examples/fixtures, manifests, README,
  project guidance, CI configuration and GitHub status. No tracked local `.env`,
  credential files, dependency trees, build output, database dumps or private
  generated artifacts were found. Standard Next.js type/guidance files are
  intentional. The local `.env` is ignored; its contents were not read.
- Heuristic scan of all locally reachable history: 114 commits and 378 unique
  blobs, including historical filenames; commit messages also checked for token,
  private-key and home-path patterns. No likely secrets found. Credential-bearing
  URLs were deliberate loopback database examples or invalid-host/test sentinels.
  Commit author/committer email metadata used GitHub noreply addresses.
- The checkout is not shallow; the only local/remote-tracking branch is `main`
  and there are no tags. This is not an exhaustive secret audit: unreachable
  objects, remote-only PR refs, hosted artifacts/log contents and external
  services were not scanned.
- All 184 pre-existing relative Markdown links and heading targets resolved.
  Former project names occur in the original charter/naming history deliberately.
  External links were not exhaustively fetched.
- [Hosted CI](https://github.com/TaoM29/runveil/actions/runs/36617663700)
  passed on the reviewed commit, including migrations, Python checks/tests,
  PostgreSQL integration, offline process-death acceptance, frontend checks/build
  and HTTP smoke. The workflow has read-only repository permissions, locked
  installs, offline fixtures and cleanup; no deployment or provider secrets are
  required. Hosted CI does not yet cover these uncommitted copy changes.
- README setup matches current configuration. Implemented runtime/reliability
  behavior is distinguished from the foundation UI, future evaluation/security
  work and unverified live AWS behavior. No public demo or benchmarks are claimed.

## Small fixes and verification

Modified `README.md` and `apps/web/app/page.tsx` to describe implemented execution
and Phase 5 completion accurately, while retaining planned-work limitations.
Updated the existing `scripts/smoke.py` home-page assertion to match the console
label; no tests were added. Removed personal absolute paths from handoffs
`PHASE_0`, `PHASE_1B`, `PHASE_1C`, `PHASE_2A`, `PHASE_2B`, `PHASE_3`, `PHASE_4A`,
`PHASE_4B`, `PHASE_5A`, `PHASE_5B` and `PHASE_5C`. Node commands now use `$HOME`;
the original charter comparison remains recorded without its attachment path.
This review is the only new file. No architectural decision or dependency changed.

Local checks passed: `npm run lint`, `npm run typecheck`, `npm test` (one existing
web test), `npm run build`, `uv run ruff format --check .`, `uv run ruff check .`,
`uv run mypy`, and `uv run python scripts/smoke.py` (API/web health, rendered home
page and unconfigured API readiness returning 503). The initial smoke run caught
the old label assertion; the corrected run passed. `npm run format:check` and
`git diff --check` also passed; the final link scan resolved all 185 relative
links and found no personal absolute paths in Markdown. Backend tests, PostgreSQL acceptance and
live services were not rerun for these presentation-only changes; current hosted
CI supplies the backend evidence. No commit, push or visibility change performed.
