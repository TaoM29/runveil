"use client";

import { useEffect, useRef, useState } from "react";
import { Status } from "../components/evidence";
import { elapsed, trace, usd, type Trace } from "../../lib/trace";

const button = "button";
const unknown = "Not recorded";

export default function TraceConsole() {
  const [runId, setRunId] = useState("");
  const [token, setToken] = useState("");
  const [view, setView] = useState<Trace | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const generation = useRef(0);
  const active = useRef<AbortController | null>(null);
  function invalidate() {
    generation.current++;
    active.current?.abort();
    active.current = null;
    setView(null);
    setBusy(false);
    setMessage("");
  }
  useEffect(() => {
    const stop = () => {
      generation.current++;
      active.current?.abort();
      active.current = null;
    };
    const forget = () => {
      stop();
      setRunId("");
      setToken("");
      setView(null);
      setBusy(false);
      setMessage("");
    };
    window.addEventListener("pagehide", forget);
    return () => {
      window.removeEventListener("pagehide", forget);
      stop();
    };
  }, []);

  async function load(next = false) {
    if (active.current || (next && view?.next_after_sequence == null)) return;
    const after = next ? view!.next_after_sequence! : 0;
    const expected = next ? view!.event_sequence : undefined;
    const id = runId.trim();
    const current = ++generation.current;
    const controller = new AbortController();
    active.current = controller;
    setBusy(true);
    setView(null);
    setMessage("");
    const timer = setTimeout(() => controller.abort(), 10000);
    try {
      const query = new URLSearchParams({ limit: "50" });
      if (next) {
        query.set("after_sequence", String(after));
        query.set("expected_sequence", String(expected));
      }
      const response = await fetch(
        `/api/traces/${encodeURIComponent(id)}?${query}`,
        {
          method: "GET",
          headers: { Authorization: `Bearer ${token}` },
          cache: "no-store",
          credentials: "omit",
          redirect: "error",
          signal: controller.signal,
        },
      );
      if (!response.ok) {
        if (current === generation.current)
          setMessage(
            response.status === 401
              ? "Trace token was refused. Use the separate read-only token."
              : response.status === 404
                ? "No run found for that ID."
                : response.status === 409
                  ? "The trace changed or is unavailable. Inspect / refresh to restart from the first event."
                  : "Trace unavailable. Check the run ID, trace token and local service configuration, then inspect again.",
          );
        return;
      }
      const result = trace(await response.json(), id, after, expected);
      if (current === generation.current) {
        setView(result);
        setMessage(
          "Recorded snapshot loaded. Refresh manually for later progress.",
        );
      }
    } catch {
      if (current === generation.current)
        setMessage(
          "Trace could not be loaded or validated. Inspect / refresh to restart. No action was taken.",
        );
    } finally {
      clearTimeout(timer);
      if (current === generation.current) {
        active.current = null;
        setBusy(false);
      }
    }
  }

  const checkpoint = view?.checkpoint;
  const tokens = checkpoint?.tokens;
  const cost = checkpoint?.cost;
  return (
    <section className="operator-console" aria-label="Trace console">
      <form
        autoComplete="off"
        className="operator-connection"
        onSubmit={(event) => {
          event.preventDefault();
          void load();
        }}
      >
        <h2>Inspect a run</h2>
        <label className="block">
          Run ID
          <input
            className="mt-1 block w-full rounded border p-2 font-mono"
            required
            spellCheck={false}
            value={runId}
            onChange={(e) => {
              invalidate();
              setRunId(e.target.value);
            }}
          />
        </label>
        <label className="block">
          Trace token
          <input
            className="mt-1 block w-full rounded border p-2"
            type="password"
            autoComplete="off"
            required
            spellCheck={false}
            value={token}
            onChange={(e) => {
              invalidate();
              setToken(e.target.value);
            }}
          />
        </label>
        <p className="text-sm text-slate-600">
          Use the separate read-only trace token. Credentials and results stay
          in this page’s memory; forget them when finished.
        </p>
        <div className="flex flex-wrap gap-3">
          <button
            className={`${button} primary`}
            disabled={busy || !token || !runId.trim()}
          >
            {busy ? "Loading…" : "Inspect / refresh"}
          </button>
          <button
            className={button}
            type="button"
            onClick={() => {
              invalidate();
              setToken("");
              setRunId("");
            }}
          >
            Forget token and trace
          </button>
        </div>
      </form>
      <p role="status" className="min-h-6 text-slate-700">
        {message}
      </p>
      {view && (
        <article className="space-y-6 rounded border border-slate-300 bg-white p-5">
          <div>
            <div className="section-heading">
              <h2>Execution snapshot</h2>
              <Status value={view.status} />
            </div>
            <p className="mt-2 break-all font-mono text-sm">{view.run_id}</p>
            <p className="mt-2 text-sm">
              Observed {view.observed_at} · Revision {view.revision} · Event
              watermark {view.event_sequence}
            </p>
          </div>
          <section className="trace-outcome space-y-2">
            <h3 className="font-semibold">Final summary</h3>
            <p className="whitespace-pre-wrap break-all [unicode-bidi:plaintext]">
              {checkpoint?.final_summary ?? "No final summary recorded"}
            </p>
            {checkpoint?.final_summary_truncated && (
              <p className="font-semibold text-amber-900">
                Summary truncated by the API at 4096 characters.
              </p>
            )}
            {checkpoint?.error_code && (
              <p className="break-all font-mono text-red-800">
                Recorded error: {checkpoint.error_code}
              </p>
            )}
          </section>
          {!view.history_complete && (
            <p className="rounded bg-amber-50 p-3 text-amber-900">
              Incomplete history: earlier execution was not recorded. This trace
              starts from the available baseline.
            </p>
          )}
          <dl className="trace-accounting">
            {[
              ["Elapsed wall time", elapsed(view.elapsed_ms)],
              ["Model intents", view.model_calls],
              ["Tool intents", view.tool_calls],
              ["Retries scheduled", checkpoint?.retries_scheduled ?? unknown],
              ["Known input tokens", tokens?.input_tokens ?? unknown],
              ["Known output tokens", tokens?.output_tokens ?? unknown],
              ["Completed model attempts", tokens?.attempts ?? unknown],
              [
                "Attempts with unknown usage",
                tokens?.unknown_attempts ?? unknown,
              ],
              [
                "Estimated cost (USD)",
                cost
                  ? `${usd(cost.known_nanousd)}${cost.unknown_attempts ? " · known subtotal" : ""}`
                  : unknown,
              ],
            ].map(([label, value]) => (
              <div key={label}>
                <dt className="text-sm text-slate-600">{label}</dt>
                <dd className="mt-1 break-words font-semibold">{value}</dd>
              </div>
            ))}
          </dl>
          <p className="text-sm text-slate-600">
            Elapsed time includes waits and downtime. Intent counts include
            unresolved calls; tokens and cost cover completed attempts at{" "}
            {checkpoint
              ? `checkpoint event ${checkpoint.event_sequence}`
              : "no recorded checkpoint"}
            . Cost is a pinned-price estimate, not an invoice.
            {cost && cost.unknown_attempts > 0
              ? ` ${cost.unknown_attempts} attempt(s) have unknown cost; the subtotal is not an exact total.`
              : ""}
          </p>
          <section className="space-y-2">
            <h3 className="font-semibold">Approval state</h3>
            <p>
              {view.approval ? view.approval.status : "No approval recorded"}
            </p>
            {view.approval && (
              <>
                <p className="break-all font-mono text-sm">
                  {view.approval.id}
                </p>
                <p className="text-sm">
                  Requested {view.approval.requested_at} · Decided{" "}
                  {view.approval.decided_at ?? "Not decided"}
                </p>
              </>
            )}
            <p className="text-sm text-slate-600">
              Approval state is descriptive. It does not grant write permission
              or prove that a file changed. Decisions require separate approval
              inspection.
            </p>
          </section>
          <details className="text-sm">
            <summary className="cursor-pointer underline">
              Run identity and timestamps
            </summary>
            <dl className="mt-3 space-y-2 break-all">
              <dt>Agent version</dt>
              <dd className="font-mono">{view.agent_version_id}</dd>
              <dt>Created</dt>
              <dd>{view.created_at}</dd>
              <dt>Started</dt>
              <dd>{view.started_at ?? unknown}</dd>
              <dt>Finished</dt>
              <dd>{view.finished_at ?? "Not finished"}</dd>
            </dl>
          </details>
          <section className="space-y-3" aria-label="Execution events">
            <h3 className="text-xl font-semibold">Execution events</h3>
            <p className="text-sm text-slate-600">
              {view.events.length
                ? `Showing events ${view.events[0].sequence}–${view.events.at(-1)!.sequence} of ${view.event_sequence}.`
                : "No events recorded."}{" "}
              Ordered by sequence. Call outcomes describe this snapshot,
              including on request events; durations measure request to
              persisted outcome, not provider latency.
            </p>
            <ol className="event-list">
              {view.events.map((event) => (
                <li
                  key={event.sequence}
                  className="space-y-2 rounded border border-slate-200 p-3 break-words [unicode-bidi:plaintext]"
                >
                  <p className="font-semibold">
                    #{event.sequence} · {event.kind}
                    {event.to_status ? ` → ${event.to_status}` : ""}
                  </p>
                  <p className="text-sm text-slate-600">
                    {event.created_at} · Revision {event.run_revision}
                    {event.step_number !== null
                      ? ` · Step ${event.step_number}`
                      : ""}
                  </p>
                  {event.invocation && (
                    <>
                      <p>
                        {event.invocation.kind === "model" ? "Model" : "Tool"}:{" "}
                        <span className="font-mono break-all">
                          {event.invocation.name}
                        </span>{" "}
                        · <strong>{event.invocation.status}</strong>
                      </p>
                      <p className="text-sm">
                        Recorded call duration:{" "}
                        {event.invocation.duration_ms === null
                          ? "Unresolved: no outcome recorded"
                          : elapsed(event.invocation.duration_ms)}
                      </p>
                      {event.invocation.error_code && (
                        <p className="font-mono text-red-800">
                          {event.invocation.error_code}
                        </p>
                      )}
                      <details className="text-sm">
                        <summary className="cursor-pointer underline">
                          Call correlation
                        </summary>
                        <p className="mt-2 break-all font-mono">
                          Call ID: {event.invocation.id}
                        </p>
                        <p>
                          Request event {event.invocation.requested_sequence} ·
                          Outcome event{" "}
                          {event.invocation.completed_sequence ??
                            "Not recorded"}
                        </p>
                        {event.invocation.provider && (
                          <p className="break-all">
                            Provider: {event.invocation.provider}
                          </p>
                        )}
                        {event.invocation.model_invocation_id && (
                          <p className="break-all font-mono">
                            Source model call:{" "}
                            {event.invocation.model_invocation_id}
                          </p>
                        )}
                      </details>
                    </>
                  )}
                  {event.retry_of && (
                    <p className="text-sm break-all font-mono">
                      Retry of: {event.retry_of}
                    </p>
                  )}
                </li>
              ))}
            </ol>
            {view.next_after_sequence !== null ? (
              <button
                className={button}
                disabled={busy}
                onClick={() => void load(true)}
              >
                Next events
              </button>
            ) : (
              <p className="text-sm">End of this recorded snapshot.</p>
            )}
            <p className="text-sm text-slate-600">
              One page is shown at a time. Inspect / refresh returns to the
              first event. If history changes, restart inspection.
            </p>
          </section>
        </article>
      )}
    </section>
  );
}
