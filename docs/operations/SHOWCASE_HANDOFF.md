# Product showcase UI handoff

Date: 2026-10-02. Base: `6d3b7af`. Implemented for review before Phase 11.
No commit or push. No Phase 11 work or public deployment.

## Result

The home page now introduces one real coding repair and the observed archive
outcomes. `/runs` provides task/fixture/run-ID search and outcome filtering over
seven retained executions. Each detail page exposes the ordered tool path, approval
decision, exact diff, complete before/after text, sandbox search matches, baseline
and post-change test logs, and identity/source provenance. Rejections and the
explicit failed-validation probe remain first-class records.

The existing operator screens share the new shell, typography, forms and focus
styles. Live traces put the final result before diagnostic accounting. Local
approvals put the exact before/after text before identity details and retain their
inspection acknowledgement and decision consequences. The approval page moved to
`/approvals`; the trace page remains `/traces`.

The showcase has no live actions. It explicitly selects public committed fixture
artifacts, labels their scripted scope, and does not broaden the trace API or add
Phase 10 browser approval. Full-document operator navigation, separate tokens,
memory-only credentials, no-store requests, late-response rejection, bounded
pagination and uncertain-decision handling remain unchanged.

See [operations and design direction](SHOWCASE.md) and
[ADR 0039](../adr/0039-recorded-product-showcase.md).

## Files

Created:

- `apps/web/lib/showcase.ts`: selected, typed presentation of the two existing
  public evidence artifacts. Source records remain unchanged.
- `apps/web/app/components/{console-shell,evidence,run-table}.tsx`: shared shell,
  labelled status/diff/test evidence and the concrete archive table.
- `apps/web/app/runs/page.tsx`, `runs/run-list.tsx`, `runs/[runId]/page.tsx`:
  archive filters and read-only detail; unknown IDs return not found.
- `apps/web/app/approvals/page.tsx`: existing approval surface at its new route.
- `apps/web/tests/showcase.test.tsx`: two focused tests for evidence fidelity,
  rejection/failure semantics, unknown IDs, filtering, reset and absence of network
  or storage side effects.
- ADR 0039, `SHOWCASE.md` and this handoff.

Modified:

- `apps/web/app/{page,layout}.tsx`, `globals.css`: overview, metadata, visual tokens,
  responsive layout and accessible control states.
- `apps/web/app/approval-console.tsx`, `traces/{page,trace-console}.tsx`: presentation
  and hierarchy; request/authority handling unchanged.
- `apps/web/tests/trace-console.test.tsx`: one expected copy string updated from
  an em dash to a colon. Existing behavioral assertions are retained.
- `scripts/smoke.py`: five production page routes and the existing security headers.
- README, ARCHITECTURE, ROADMAP, DEVELOPMENT, TRACES and APPROVAL_CONSOLE: current routes,
  evidence boundaries and review gate.

No dependencies, backend/API/proxy code, runtime, fixtures, database schema or
source evidence files changed. No speculative UI framework or additional controls.

## Verification

| Check                                                                        | Result                                                                                                            |
| ---------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------- |
| `npm run lint`                                                               | Passed                                                                                                            |
| `npm run typecheck`                                                          | Passed                                                                                                            |
| `npm test`                                                                   | 13 passed, including the existing proxy, stale-response, credential, pagination and exact decision-binding checks |
| `npm run build`                                                              | Passed; overview, archive, seven detail pages and operator routes render                                          |
| `npm run format:check`                                                       | Passed                                                                                                            |
| `uv run ruff format --check .` / `uv run ruff check .`                       | Passed                                                                                                            |
| `uv run mypy`                                                                | Passed, 138 source files                                                                                          |
| `uv run python scripts/smoke.py` with the retained local PostgreSQL database | Passed API/web health, all five page types, frame/referrer headers and readiness                                  |
| `git diff --check`                                                           | Passed                                                                                                            |

Browser checks used the production build on loopback, not a mocked visual preview:

- Overview to the complete clamp run; exact before/after disclosure opens; the
  diff and baseline/validation output match the recorded artifact.
- Outcome filtering shows three rejected runs; a nonmatching search shows an
  actionable empty state; Clear filters restores all seven; failed-validation
  filtering opens the explicitly labelled, applied-but-failed mean record.
- Layout inspected at 1440, 1280 and 320 CSS pixels. No document overflow in the
  checked archive, run detail or live trace views. Tables retain bounded horizontal
  scrolling, an explicit mobile cue and a focusable scroll region. Code and long
  digests wrap without clipping.
- A real retained Phase 10G run loads through the existing authenticated live API:
  47 events, the recorded passing summary and preserved accounting. Keyboard Tab
  reaches Forget with a visible solid focus indicator; Enter clears all inputs
  and the snapshot. Local approval service refusal gives a recovery instruction,
  and Forget clears the attempted inputs.
- No browser warning/error logs observed in these checks.

Rendered contrast pairs were read from the browser and calculated with the WCAG
relative-luminance formula: heading/page 14.81:1; muted text/evidence surface 5.99:1;
primary action 7.89:1; success 6.48:1; danger 6.66:1; notice 5.33:1. The declared
warning pair is 6.38:1, input border/white 3.10:1 and focus/white 7.89:1.
Status also has a text label; diff additions/removals retain their signs.

Full backend/integration/Docker acceptance was not rerun: those implementations
are unchanged. Successful live approval decisions were verified by the existing
component/proxy tests, not submitted through the browser during this slice.
No manual screen-reader, actual browser 200% zoom, RTL, Safari or Firefox pass is
claimed. Narrow reflow and native control semantics were checked as described.

## Design review and antislop guardrail

Resolved scope: the overview-to-record flow, archive filters and existing operator
surfaces. Next App Router, React, Tailwind and plain CSS; no added UI dependency.
The charter, architecture, ADRs 0024–0027/0038, web AGENTS and bundled Next docs were
reviewed before implementation. The user's operations-console direction governs;
antislop is a quality filter, not the visual style.

| Domain        | Evidence                                                                                                               | Assessment                                                              |
| ------------- | ---------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------- |
| Accessibility | Native controls, visible focus, labels, status region, text outcomes, exact disclosures; browser keyboard/320px checks | No blocking finding in checked scope; manual screen reader not verified |
| Layout        | Desktop and narrow browser views; shared alignment, stacked evidence, bounded table scrolling                          | Clear in checked widths                                                 |
| Writing       | Real outcomes, fault-injection/source labels, separate authority, recoverable errors                                   | Clear                                                                   |
| Typography    | System sans hierarchy, code-only monospace, tabular accounting, wrapping IDs/code                                      | Clear                                                                   |
| Color         | Measured rendered pairs and explicit semantic labels                                                                   | Clear for checked pairs                                                 |
| UI polish     | Overview, detail, filtering/reset, disclosure, live result/refusal/forget states                                       | Clear; no animation beyond optional button feedback                     |

Guardrail delivery checks:

- **Hard gate PASS (checked scope):** real source records and derived counts, no
  invented functionality/claims/assets, functional destinations, labelled native
  controls, visible focus and measured contrast. No application text uses a new
  em dash; source artifact text remains exact. Narrow layouts do not overflow the
  document. No claim is made for the unverified environments listed above.
- **Purpose gate PASS:** the execution rail explains ordering, the diff encodes
  exact changes, and the table compares observed outcomes. The summary counts the
  actual archive. Borders group evidence; accent color identifies actions and
  navigation. No decorative chart, fake terminal, activity feed, gradient or glow.
- **Liveliness PASS:** ENERGY 2 / RHYTHM 2 / MOTION 1. The repair is the focal point;
  source/test evidence and the ordered execution path give the console its identity.
  Section spacing separates overview, evidence and provenance without a repeated
  marketing-card template.
- **Craftsmanship PASS (checked scope):** all shipped controls have behavior;
  content is attributable to committed records; public evidence and local authority
  are visibly distinct; focus, refusal and empty states have usable recovery paths.

Verdict: ready for review within this verification coverage. No blocking interface
finding remains in the inspected flow; the unverified environments remain explicit.

## Next step and operational limits

Review the visual result and the recorded-vs-live distinction before moving to
Phase 11. Public hosting, live run discovery, Phase 10 browser decisions and
multi-user access are separate work, not implied by this showcase.

Verification reused `runveil-phase10g_postgres_data` read-only through the trace
API; no runs or decisions were created. The temporary API/credential and dedicated
PostgreSQL service are cleaned up after verification; the volume is preserved.
The read-only web preview remains at `http://127.0.0.1:3100` for review, without a
configured operator API. No commit or push.
