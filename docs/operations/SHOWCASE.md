# Product showcase and local console

The web home page now presents recorded Phase 10 coding executions. It runs without
a database or API token. The records are real, committed acceptance evidence from
02 October 2026, using public project fixtures and a scripted provider. They are
not a live activity feed or a model-quality benchmark.

## Start and explore

Use the Node version in `.nvmrc`, then run `npm run dev:web` from the repository
root. Open `http://localhost:3000`. For a production preview, run `npm run build`
and `npm run start --workspace @runveil/web`.

- `/`: overview, observed counts and the clamp repair from baseline to validation.
- `/runs`: search by task, fixture or run ID; filter by passed, rejected or failed
  validation. These controls operate only on the retained archive.
- `/runs/[runId]`: ordered tool execution, recorded approval decision, exact diff,
  complete before/after text, search matches, baseline/post-change test logs and
  provenance. Unknown IDs have no record and return not found.
- `/traces`: authenticated read-only inspection of an existing local run, using
  the separate trace token. It intentionally omits raw proposals and tool output.
- `/approvals`: the existing local approval console, moved from `/`. Its supported
  Phase 6 profiles and authorization behavior are unchanged. Phase 10 sandbox
  approval remains in the worker CLI.

A useful demo is the successful clamp record, a rejected record, then the mean
validation-failure probe. The latter deliberately proposed an ineffective patch:
application succeeded but validation failed. Approval, mutation and test success
are separate facts throughout the UI. A rejected proposal has no post-change tests.

## Evidence boundary

`apps/web/lib/showcase.ts` explicitly imports only:

- `docs/operations/evidence/phase10g/tasks.json`: three approved repairs and three
  rejections, including the sandbox search stage.
- `docs/operations/evidence/phase10f/failed-validation.json`: one labelled failure
  probe using the earlier profile, which has no search stage.

The view projects known fields; it does not enumerate evidence directories, query
the database, load local paths selected by a visitor or expose the live trace's
private fields. Adding another artifact requires reviewing its public contents
and updating that explicit source selection. Do not import operational dumps or
credentials. Original evidence stays authoritative and is not rewritten for display.

Operator tokens stay in each page's memory. Navigation uses full-document links
across operator surfaces, Forget clears the token and view, and late responses are
still discarded. The archive offers no approval buttons. Local deployment remains
loopback-only; a public portfolio presentation is not a public deployment approval
for the operator API. See [ADR 0039](../adr/0039-recorded-product-showcase.md).

## Design direction

The screen's job is to explain what happened and let a reviewer inspect why. The
visual system uses an ordered execution rail and source/test evidence, rather than
charts or activity feeds without underlying data. One compact summary strip counts
the actual archive; the main emphasis is the repair and its outcome.

System sans keeps dense operational text readable without network-loaded fonts.
Monospace is limited to code, paths and IDs. Light neutral surfaces retain the
existing console's character; indigo identifies actions/navigation, while green,
amber and red always pair with outcome labels. Borders group evidence; no decorative
shadow, illustration, invented logo or animation is needed. CSS tokens live in
`apps/web/app/globals.css`. Native links, buttons, selects and disclosures provide
keyboard behavior. At narrow widths, columns stack; the evidence table retains
horizontal scrolling with a visible instruction and keyboard focus target.

The interface/layout/type/color/accessibility skills guided implementation.
Antislop ran during implementation as a guardrail. Design dials: ENERGY 2,
RHYTHM 2, MOTION 1. Motion is limited to short optional button color transitions.
See [handoff and verification](SHOWCASE_HANDOFF.md) for coverage and limits.
