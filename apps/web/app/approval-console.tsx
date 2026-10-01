"use client";

import { useEffect, useRef, useState } from "react";
import { consequences, inspection, type Inspection } from "../lib/approval";

const button =
  "rounded border border-slate-400 px-4 py-2 font-medium disabled:opacity-40 focus-visible:outline-2 focus-visible:outline-offset-4";

export default function ApprovalConsole() {
  const [token, setToken] = useState("");
  const [runId, setRunId] = useState("");
  const [view, setView] = useState<Inspection | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [reviewed, setReviewed] = useState(false);
  const generation = useRef(0);
  const active = useRef<AbortController | null>(null);
  const decisionInFlight = useRef(false);

  function invalidate() {
    const uncertain = decisionInFlight.current;
    decisionInFlight.current = false;
    generation.current++;
    active.current?.abort();
    active.current = null;
    setBusy(false);
    setView(null);
    setReviewed(false);
    setMessage(
      uncertain
        ? "A decision was in progress. Its outcome may be unknown; inspect the original run again."
        : "",
    );
  }
  useEffect(() => {
    const stop = () => {
      generation.current++;
      active.current?.abort();
      active.current = null;
    };
    const forget = () => {
      const uncertain = decisionInFlight.current;
      decisionInFlight.current = false;
      stop();
      setToken("");
      setView(null);
      setReviewed(false);
      setBusy(false);
      setMessage(
        uncertain
          ? "A decision was in progress. Its outcome may be unknown; inspect the original run again."
          : "",
      );
    };
    window.addEventListener("pagehide", forget);
    return () => {
      window.removeEventListener("pagehide", forget);
      stop();
    };
  }, []);

  async function load(decision?: "APPROVED" | "REJECTED") {
    if (active.current || (decision && (!view || !reviewed))) return;
    const observed = view;
    const id = runId.trim();
    const current = ++generation.current;
    const controller = new AbortController();
    active.current = controller;
    decisionInFlight.current = Boolean(decision);
    setBusy(true);
    setView(null);
    setReviewed(false);
    setMessage("");
    const timer = setTimeout(() => controller.abort(), 10000);
    try {
      const response = await fetch(`/api/approvals/${encodeURIComponent(id)}`, {
        method: decision ? "POST" : "GET",
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
        },
        body:
          decision && observed
            ? JSON.stringify({
                decision,
                expected_profile: observed.profile,
                expected_approval_id: observed.request.id,
                expected_revision: observed.run_revision,
                expected_digest: observed.request.digest,
              })
            : undefined,
        cache: "no-store",
        credentials: "omit",
        redirect: "error",
        signal: controller.signal,
      });
      if (!response.ok) {
        const reason =
          response.status === 401
            ? "Operator token was refused."
            : response.status === 404
              ? "No approval found for that run."
              : response.status === 409
                ? "The approval changed or can no longer be decided."
                : "The approval service could not complete the request.";
        throw Error(reason);
      }
      const result = inspection(await response.json(), id);
      if (current === generation.current) {
        setView(result);
        setMessage(
          decision
            ? "Decision recorded. Refresh to inspect later worker progress."
            : "Inspection loaded. Read the full proposal and its consequences before deciding.",
        );
      }
    } catch (error) {
      if (current === generation.current)
        setMessage(
          (error instanceof Error &&
          [
            "Operator token was refused.",
            "No approval found for that run.",
            "The approval changed or can no longer be decided.",
          ].includes(error.message)
            ? error.message
            : "The approval service could not complete the request.") +
            (decision
              ? " The decision outcome may be unknown. Inspect again before taking any further action."
              : " Check the run ID, token and local service configuration, then inspect again."),
        );
    } finally {
      clearTimeout(timer);
      if (current === generation.current) {
        active.current = null;
        decisionInFlight.current = false;
        setBusy(false);
      }
    }
  }

  return (
    <section className="mt-8 space-y-6" aria-label="Approval console">
      <form
        className="space-y-4 rounded border border-slate-300 bg-white p-5"
        onSubmit={(event) => {
          event.preventDefault();
          void load();
        }}
        autoComplete="off"
      >
        <label className="block">
          Run ID
          <input
            className="mt-1 block w-full rounded border p-2 font-mono"
            required
            value={runId}
            onChange={(e) => {
              invalidate();
              setRunId(e.target.value);
            }}
            spellCheck={false}
          />
        </label>
        <label className="block">
          Operator token
          <input
            className="mt-1 block w-full rounded border p-2"
            type="password"
            autoComplete="off"
            required
            value={token}
            onChange={(e) => {
              invalidate();
              setToken(e.target.value);
            }}
            spellCheck={false}
          />
        </label>
        <p className="text-sm text-slate-600">
          Token and proposal stay in this page’s memory. Forget them when
          finished. Use this console only on your trusted local machine.
        </p>
        <div className="flex flex-wrap gap-3">
          <button className={button} disabled={busy || !token || !runId.trim()}>
            {busy ? "Request in progress…" : "Inspect / refresh"}
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
            Forget token and proposal
          </button>
        </div>
      </form>
      <p role="status" className="min-h-6 text-slate-700">
        {message}
      </p>
      {view && (
        <article className="space-y-5 rounded border border-slate-300 bg-white p-5">
          <h2 className="text-xl font-semibold">
            Proposal:{" "}
            <span className="break-all font-mono">
              {view.request.proposal.path}
            </span>
          </h2>
          <p>
            Run: <strong>{view.run_status}</strong> · Approval:{" "}
            <strong>{view.request.status}</strong> · Revision{" "}
            {view.run_revision}
          </p>
          <p className="rounded bg-slate-100 p-3">
            {consequences[view.profile]}
          </p>
          <dl className="space-y-2 break-all text-sm">
            <dt>Profile</dt>
            <dd className="font-mono">{view.profile}</dd>
            <dt>Approval ID</dt>
            <dd className="font-mono">{view.request.id}</dd>
            <dt>Proposal digest</dt>
            <dd className="font-mono">{view.request.digest}</dd>
            {view.workspace &&
              Object.entries(view.workspace).map(([key, value]) => (
                <div key={key}>
                  <dt>{key}</dt>
                  <dd className="font-mono">{value}</dd>
                </div>
              ))}
          </dl>
          {view.workspace && (
            <p className="text-sm">
              These fingerprints identify the pinned workspace. Inspection does
              not check current files.
            </p>
          )}
          <div className="grid gap-4 md:grid-cols-2">
            {(["before", "after"] as const).map((part) => (
              <section key={part}>
                <h3 className="mb-2 font-semibold">
                  {part === "before" ? "Before" : "After"}
                </h3>
                <pre className="max-h-96 overflow-auto whitespace-pre-wrap break-all rounded border bg-slate-50 p-3 text-sm [unicode-bidi:plaintext]">
                  {view.request.proposal[part]}
                </pre>
              </section>
            ))}
          </div>
          <details>
            <summary className="cursor-pointer underline">
              Exact escaped text (including whitespace)
            </summary>
            <pre className="mt-2 max-h-96 overflow-auto whitespace-pre-wrap break-all text-sm">
              {JSON.stringify(view.request.proposal, null, 2).replace(
                /[\u007f-\uffff]/g,
                (character) =>
                  `\\u${character.charCodeAt(0).toString(16).padStart(4, "0")}`,
              )}
            </pre>
          </details>
          <p>
            Mutation:{" "}
            {view.mutation
              ? `${view.mutation.status}${view.mutation.error_code ? ` · ${view.mutation.error_code}` : ""}`
              : "No mutation intent recorded in this inspection."}
          </p>
          {view.mutation && view.mutation.status !== "SUCCEEDED" && (
            <p className="font-semibold text-amber-900">
              File contents may already have changed. A failed or uncertain
              mutation is not evidence that the file is unchanged. Do not replay
              it.
            </p>
          )}
          {view.request.status === "PENDING" &&
            view.run_status === "WAITING_FOR_APPROVAL" && (
              <div className="space-y-3 border-t pt-4">
                <label className="flex items-start gap-2">
                  <input
                    type="checkbox"
                    className="mt-1"
                    checked={reviewed}
                    onChange={(e) => setReviewed(e.target.checked)}
                  />
                  I inspected the complete before/after text, workspace identity
                  and approval consequences.
                </label>
                <p className="text-sm">
                  Rejecting terminates this pending workflow. Approval does not
                  extend its deadline.
                </p>
                <div className="flex gap-3">
                  <button
                    className={button}
                    disabled={!reviewed || busy}
                    onClick={() => void load("APPROVED")}
                  >
                    Approve proposal
                  </button>
                  <button
                    className={button}
                    disabled={!reviewed || busy}
                    onClick={() => void load("REJECTED")}
                  >
                    Reject proposal
                  </button>
                </div>
              </div>
            )}
        </article>
      )}
    </section>
  );
}
