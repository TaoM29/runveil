// @vitest-environment jsdom
import { randomBytes, randomUUID } from "node:crypto";
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import ApprovalConsole from "../app/approval-console";

let container: HTMLDivElement;
let root: Root;
const runId = randomUUID();
const payload = {
  profile: "repository-patch-v1",
  run_status: "WAITING_FOR_APPROVAL",
  run_revision: 2,
  request: {
    id: randomUUID(),
    run_id: runId,
    digest: "a".repeat(64),
    status: "PENDING",
    proposal: {
      schema_version: 1,
      path: "a.txt",
      before: "<script>not executable</script>\n",
      after: "new text\n",
    },
  },
  workspace: {
    root_digest: "b".repeat(64),
    content_digest: "c".repeat(64),
    implementation_digest: "d".repeat(64),
  },
  mutation: null,
};
beforeEach(async () => {
  vi.stubGlobal("IS_REACT_ACT_ENVIRONMENT", true);
  container = document.createElement("div");
  document.body.append(container);
  root = createRoot(container);
  await act(async () => root.render(<ApprovalConsole />));
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
  const result = [...container.querySelectorAll("button")].find(
    (item) => item.textContent === text,
  );
  if (!result) throw Error(`Missing button: ${text}`);
  return result;
}
async function inspect() {
  await enter(0, runId);
  await enter(1, randomBytes(32).toString("base64url"));
  await act(async () => button("Inspect / refresh").click());
}
it("renders escaped exact text, binds decisions to inspection, and requires refresh after uncertain outcomes", async () => {
  const fetch = vi
    .fn()
    .mockResolvedValueOnce(Response.json(payload))
    .mockRejectedValueOnce(Error("private transport detail"));
  vi.stubGlobal("fetch", fetch);
  await inspect();
  expect(container.querySelector("script")).toBeNull();
  expect(container.textContent).toContain(payload.request.proposal.before);
  expect(container.textContent).toContain("separately started worker");
  expect(button("Approve proposal").disabled).toBe(true);
  await act(async () =>
    container
      .querySelector<HTMLInputElement>('input[type="checkbox"]')!
      .click(),
  );
  await act(async () => button("Approve proposal").click());
  expect(JSON.parse(fetch.mock.calls[1][1].body)).toEqual({
    decision: "APPROVED",
    expected_profile: payload.profile,
    expected_approval_id: payload.request.id,
    expected_revision: 2,
    expected_digest: payload.request.digest,
  });
  expect(container.textContent).toContain("outcome may be unknown");
  expect(container.textContent).not.toContain("private transport detail");
  expect(container.querySelector("article")).toBeNull();
  expect(fetch).toHaveBeenCalledTimes(2);
  fetch.mockResolvedValueOnce(
    Response.json({
      ...payload,
      request: { ...payload.request, run_id: randomUUID() },
    }),
  );
  await act(async () => button("Inspect / refresh").click());
  expect(container.querySelector("article")).toBeNull();
  await act(async () => button("Forget token and proposal").click());
  expect(
    container.querySelector<HTMLInputElement>('input[type="password"]')!.value,
  ).toBe("");
  expect(localStorage.length).toBe(0);
  expect(sessionStorage.length).toBe(0);
});

it("discards stale responses when inputs change and clears credentials on pagehide", async () => {
  let resolve!: (response: Response) => void;
  const fetch = vi.fn().mockReturnValue(
    new Promise<Response>((done) => {
      resolve = done;
    }),
  );
  vi.stubGlobal("fetch", fetch);
  await inspect();
  await enter(0, randomUUID());
  await act(async () => resolve(Response.json(payload)));
  expect(container.querySelector("article")).toBeNull();
  fetch.mockResolvedValueOnce(Response.json(payload));
  await enter(0, runId);
  await act(async () => button("Inspect / refresh").click());
  await act(async () =>
    container
      .querySelector<HTMLInputElement>('input[type="checkbox"]')!
      .click(),
  );
  fetch.mockReturnValueOnce(
    new Promise<Response>((done) => {
      resolve = done;
    }),
  );
  await act(async () => button("Reject proposal").click());
  await enter(1, randomBytes(32).toString("base64url"));
  await act(async () => resolve(Response.json(payload)));
  expect(container.textContent).toContain("inspect the original run again");
  expect(container.querySelector("article")).toBeNull();
  await act(async () => window.dispatchEvent(new Event("pagehide")));
  expect(
    container.querySelector<HTMLInputElement>('input[type="password"]')!.value,
  ).toBe("");
  expect(button("Inspect / refresh").disabled).toBe(true);
});
