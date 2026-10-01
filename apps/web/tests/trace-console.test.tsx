// @vitest-environment jsdom
import { randomBytes, randomUUID } from "node:crypto";
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import TraceConsole from "../app/traces/trace-console";
import { trace, type Trace } from "../lib/trace";
const runId = randomUUID(),
  callId = randomUUID();
const at = "2026-10-01T10:00:00Z";
const call = {
  id: callId,
  kind: "model" as const,
  name: "fixture",
  provider: "scripted",
  model_invocation_id: null,
  status: "FAILED",
  requested_sequence: 2,
  completed_sequence: 3,
  requested_at: at,
  completed_at: at,
  duration_ms: 0,
  error_code: "execution_interrupted",
};
const payload: Trace = {
  schema_version: 1,
  run_id: runId,
  agent_version_id: randomUUID(),
  status: "FAILED",
  revision: 2,
  created_at: at,
  started_at: at,
  finished_at: at,
  observed_at: at,
  elapsed_ms: 0,
  event_sequence: 3,
  history_complete: false,
  model_calls: 1,
  tool_calls: 0,
  checkpoint: {
    event_sequence: 3,
    schema_version: 6,
    tokens: {
      attempts: 1,
      input_tokens: 0,
      output_tokens: 0,
      unknown_attempts: 1,
    },
    cost: { known_nanousd: 12500, unknown_attempts: 1 },
    retries_scheduled: 0,
    error_code: "execution_interrupted",
    final_summary: "<script>untrusted text</script>",
    final_summary_truncated: true,
  },
  approval: {
    id: randomUUID(),
    status: "APPROVED",
    requested_at: at,
    decided_at: at,
  },
  events: [
    {
      sequence: 1,
      kind: "run.snapshot",
      run_revision: 0,
      step_number: null,
      created_at: at,
      retry_of: null,
      to_status: "RUNNING",
      invocation: null,
    },
    {
      sequence: 2,
      kind: "model.requested",
      run_revision: 1,
      step_number: null,
      created_at: at,
      retry_of: randomUUID(),
      to_status: null,
      invocation: call,
    },
  ],
  next_after_sequence: 2,
};
const last: Trace = {
  ...payload,
  events: [
    { ...payload.events[1], sequence: 3, kind: "model.failed", retry_of: null },
  ],
  next_after_sequence: null,
};
let root: Root, container: HTMLDivElement;
beforeEach(async () => {
  vi.stubGlobal("IS_REACT_ACT_ENVIRONMENT", true);
  container = document.createElement("div");
  document.body.append(container);
  root = createRoot(container);
  await act(async () => root.render(<TraceConsole />));
});
afterEach(async () => {
  await act(async () => root.unmount());
  container.remove();
  vi.unstubAllGlobals();
});
async function enter(index: number, value: string) {
  await act(async () => {
    const input = container.querySelectorAll("input")[index];
    Object.getOwnPropertyDescriptor(
      HTMLInputElement.prototype,
      "value",
    )!.set!.call(input, value);
    input.dispatchEvent(new Event("input", { bubbles: true }));
  });
}
function button(text: string) {
  const found = [...container.querySelectorAll("button")].find(
    (b) => b.textContent === text,
  );
  if (!found) throw Error(`Missing ${text}`);
  return found;
}
async function inspect() {
  await enter(0, runId);
  await enter(1, randomBytes(32).toString("base64url"));
  await act(async () => button("Inspect / refresh").click());
}
it("shows safe evidence and unknown accounting, binds pages, and clears the snapshot on conflict", async () => {
  const fetch = vi
    .fn()
    .mockResolvedValueOnce(Response.json(payload))
    .mockResolvedValueOnce(Response.json(last))
    .mockResolvedValueOnce(new Response("private", { status: 409 }));
  vi.stubGlobal("fetch", fetch);
  await inspect();
  expect(container.querySelector("script")).toBeNull();
  expect(container.textContent).toContain("<script>untrusted text</script>");
  expect(container.textContent).toContain("$0.000012500 · known subtotal");
  expect(container.textContent).toContain("not an exact total");
  expect(container.textContent).toContain("Incomplete history");
  expect(container.textContent).toContain("Summary truncated");
  expect(container.textContent).toContain("Retry of:");
  expect(container.textContent).toContain("does not grant write permission");
  await act(async () => button("Next events").click());
  expect(fetch.mock.calls[1][0]).toBe(
    `/api/traces/${runId}?limit=50&after_sequence=2&expected_sequence=3`,
  );
  expect(container.textContent).toContain("Showing events 3–3");
  expect(container.textContent).not.toContain("#1 ·");
  expect(container.textContent).toContain("End of this recorded snapshot");
  await act(async () => button("Inspect / refresh").click());
  expect(container.querySelector("article")).toBeNull();
  expect(container.textContent).toContain("restart from the first event");
  expect(container.textContent).not.toContain("private");
  expect(
    fetch.mock.calls.every(
      ([, options]) =>
        options.method === "GET" && options.credentials === "omit",
    ),
  ).toBe(true);
});
it("discards late responses after edits/forget/pagehide and never stores credentials", async () => {
  let resolve!: (response: Response) => void;
  const fetch = vi.fn().mockImplementation(
    () =>
      new Promise<Response>((done) => {
        resolve = done;
      }),
  );
  vi.stubGlobal("fetch", fetch);
  await inspect();
  await enter(0, randomUUID());
  await act(async () => resolve(Response.json(payload)));
  expect(container.querySelector("article")).toBeNull();
  await inspect();
  await enter(1, randomBytes(32).toString("base64url"));
  await act(async () => resolve(Response.json(payload)));
  expect(container.querySelector("article")).toBeNull();
  await inspect();
  await act(async () => button("Forget token and trace").click());
  await act(async () => resolve(Response.json(payload)));
  expect(container.querySelector("article")).toBeNull();
  await inspect();
  await act(async () => window.dispatchEvent(new Event("pagehide")));
  await act(async () => resolve(Response.json(payload)));
  expect(container.querySelector("article")).toBeNull();
  expect(
    [...container.querySelectorAll("input")].every((i) => i.value === ""),
  ).toBe(true);
  expect(localStorage.length).toBe(0);
  expect(sessionStorage.length).toBe(0);
});
it("rejects malformed, foreign, unsafe-number and mismatched-page responses without displaying them", async () => {
  for (const value of [
    { ...payload, run_id: randomUUID() },
    { ...payload, schema_version: 2 },
    { ...payload, model_calls: Number.MAX_SAFE_INTEGER + 1 },
    { ...payload, events: [payload.events[1], payload.events[0]] },
    { ...payload, next_after_sequence: 1 },
  ])
    expect(() => trace(value, runId)).toThrow("Invalid trace");
  expect(() => trace(last, runId, 2, 4)).toThrow("Invalid trace");
  const fetch = vi
    .fn()
    .mockResolvedValueOnce(
      Response.json({
        ...payload,
        checkpoint: null,
        approval: null,
        events: payload.events.map((e) => ({
          ...e,
          invocation: e.invocation
            ? {
                ...call,
                status: "REQUESTED",
                completed_sequence: null,
                completed_at: null,
                duration_ms: null,
                error_code: null,
              }
            : null,
        })),
      }),
    )
    .mockResolvedValueOnce(Response.json({ ...last, event_sequence: 4 }));
  vi.stubGlobal("fetch", fetch);
  await inspect();
  expect(container.textContent).toContain("Not recorded");
  expect(container.textContent).toContain("Unresolved — no outcome recorded");
  await act(async () => button("Next events").click());
  expect(container.querySelector("article")).toBeNull();
  expect(container.textContent).toContain("could not be loaded or validated");
});
