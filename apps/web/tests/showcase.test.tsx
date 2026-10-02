// @vitest-environment jsdom
import { act } from "react";
import { createRoot } from "react-dom/client";
import { renderToStaticMarkup } from "react-dom/server";
import { expect, it, vi } from "vitest";
import RunList from "../app/runs/run-list";
import RunPage from "../app/runs/[runId]/page";
import { showcaseRuns } from "../lib/showcase";
import evidence from "../../../docs/operations/evidence/phase10g/tasks.json";

vi.mock("next/navigation", () => ({
  notFound: () => {
    throw Error("not found");
  },
}));

it("presents exact committed evidence without offering decisions, including rejection and failed validation", async () => {
  const approved = showcaseRuns[0];
  expect(approved.diff).toBe(evidence.runs[0].final.diff);
  expect(approved.search?.matches).toEqual(
    evidence.runs[0].final.tools[1].result.matches,
  );
  for (const run of showcaseRuns) {
    const html = renderToStaticMarkup(
      await RunPage({ params: Promise.resolve({ runId: run.id }) }),
    );
    const container = document.createElement("div");
    container.innerHTML = html;
    expect(container.textContent).toContain(run.approval.digest);
    expect(container.querySelector(".diff-code")?.textContent).toBe(run.diff);
    expect(container.textContent).toContain(run.baseline?.output);
    expect(container.querySelector("button")).toBeNull();
    if (run.outcome === "Rejected") {
      expect(run.applied).toBe(false);
      expect(container.textContent).toContain(
        "Proposal rejected. No mutation.",
      );
      expect(container.textContent).toContain(
        "Not run. The proposal was rejected",
      );
    }
    if (run.faultInjection) {
      expect(run.applied).toBe(true);
      expect(run.search).toBeNull();
      expect(container.textContent).toContain(
        "Patch applied. Validation failed.",
      );
      expect(container.textContent).toContain("Fault injection:");
    }
  }
  await expect(
    RunPage({ params: Promise.resolve({ runId: "unknown" }) }),
  ).rejects.toThrow("not found");
});

it("filters recorded runs, announces empty results and restores them without network requests or storage", async () => {
  vi.stubGlobal("IS_REACT_ACT_ENVIRONMENT", true);
  const fetch = vi.fn();
  vi.stubGlobal("fetch", fetch);
  const container = document.createElement("div");
  document.body.append(container);
  const root = createRoot(container);
  try {
    await act(async () => root.render(<RunList runs={showcaseRuns} />));
    const select = container.querySelector("select")!;
    await act(async () => {
      select.value = "Rejected";
      select.dispatchEvent(new Event("change", { bubbles: true }));
    });
    expect(container.querySelector('[role="status"]')?.textContent).toBe(
      "3 of 7 runs",
    );
    const input = container.querySelector("input")!;
    await act(async () => {
      Object.getOwnPropertyDescriptor(
        HTMLInputElement.prototype,
        "value",
      )!.set!.call(input, "no-such-task");
      input.dispatchEvent(new Event("input", { bubbles: true }));
    });
    expect(container.textContent).toContain("No matching runs");
    await act(async () => container.querySelector("button")!.click());
    expect(container.querySelector('[role="status"]')?.textContent).toBe(
      "7 of 7 runs",
    );
    expect(fetch).not.toHaveBeenCalled();
    expect(localStorage.length).toBe(0);
    expect(sessionStorage.length).toBe(0);
  } finally {
    await act(async () => root.unmount());
    container.remove();
    vi.unstubAllGlobals();
  }
});
