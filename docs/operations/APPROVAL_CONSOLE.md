# Local approval console

The home page is a single-run operator console for the
[existing approval API](APPROVAL_API.md). It has no submit, start-worker or write-grant
control. The local shared token authorizes all supported approvals in that API
installation, not an individually identified reviewer.

## Start

Follow [development setup](DEVELOPMENT.md) and [API setup](APPROVAL_API.md) to start
the API on loopback with a generated operator token. In the web terminal:

```sh
export RUNVEIL_API_ORIGIN=http://127.0.0.1:8000
npm run dev:web
```

For production-mode local verification, use `npm run build` and
`npm run start --workspace @runveil/web` with the same origin environment variable.
Only the literal `http://127.0.0.1:<port>` API target is supported. Do not expose
these services publicly or place them behind a remote proxy without a separate
security/deployment review. Keep request headers/bodies out of logs and traces.
The web process does not need `RUNVEIL_APPROVAL_TOKEN`; it forwards the token entered
by the caller. The API still performs authentication. A missing target disables
proxy operations, and a missing API token disables the API independently.

Open the console at `http://localhost:3000` (or its configured loopback port).
Enter the run ID from the [review](APPROVALS.md) or [patch](PATCHES.md) CLI and the
operator token. The token is password-masked and stays in page memory; avoid saving
it in your browser's password manager. No automatic run discovery is performed.

## Inspect and decide

1. Select **Inspect / refresh**. Read the full before/after text, path, profile,
   approval ID, digest and workspace fingerprints. The escaped-text disclosure
   shows newlines and whitespace explicitly. Proposal text is never executed as HTML.
2. Check the profile consequence: standalone review completes without writing;
   worker review continues without writing; patch approval permits the exact
   replacement only when a later worker has a separate write grant and matching
   workspace. The UI never starts that worker or extends its original deadline.
3. Acknowledge inspection, then choose **Approve proposal** or **Reject proposal**.
   Rejection terminates the pending workflow. The decision submits the inspected
   identity/profile/revision/digest; none is editable in the decision controls.
4. Run the appropriate worker separately if approved. Refresh to inspect progress.
   `APPROVED` alone does not mean a file was changed. A failed or uncertain mutation
   may already have changed it; never replay uncertain work based on current text.
5. Select **Forget token and proposal** when finished. Leaving the page also clears
   the token and inspection. Browser extensions/password managers remain outside
   the application's memory-only guarantee.

Changing either input clears inspection and acknowledgement. Only one request can
be active in the page. A response from an abandoned request is ignored. If a
request fails or a decision is interrupted, the page cannot determine whether the
database committed; inspect the original run again. Do not retry a decision blindly.
No polling or automatic retry is performed. API conflicts do not re-enable the
old decision controls.

## Verification scope

React DOM tests cover escaped content, exact decision bindings, acknowledgement,
uncertain outcome, stale responses, input changes, pagehide and forget. Proxy tests
cover destination/origin/authentication checks, credential-only forwarding, request
and response limits, timeout, safe errors and no-store behavior. Production-server
smoke checks verify framing/referrer headers. See [Phase 6E handoff](PHASE_6E.md) for
real web/API/database/worker acceptance evidence and remaining browser coverage.
