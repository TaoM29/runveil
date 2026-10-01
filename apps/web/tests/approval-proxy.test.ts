import { randomBytes, randomUUID } from "node:crypto";
import { afterEach, expect, it, vi } from "vitest";
import { GET, POST } from "../app/api/approvals/[runId]/route";

const runId = randomUUID();
const context = { params: Promise.resolve({ runId }) };
const url = `http://localhost:3000/api/approvals/${runId}`;
const token = randomBytes(32).toString("base64url");
function request(
  method = "GET",
  extra: Record<string, string> = {},
  body?: string,
) {
  return new Request(url, {
    method,
    headers: {
      Authorization: `Bearer ${token}`,
      Origin: "http://localhost:3000",
      "Content-Type": "application/json",
      ...extra,
    },
    body,
  });
}
afterEach(() => {
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
  vi.useRealTimers();
});

it("forwards only caller credentials to a fixed local endpoint, with no caching or redirects", async () => {
  vi.stubEnv("RUNVEIL_API_ORIGIN", "http://127.0.0.1:8000");
  const fetch = vi.fn().mockResolvedValue(
    Response.json(
      { inspected: true },
      {
        headers: { "Set-Cookie": "untrusted", Location: "http://elsewhere" },
      },
    ),
  );
  vi.stubGlobal("fetch", fetch);
  const response = await POST(
    request(
      "POST",
      {
        Cookie: "ambient=ignored",
        Host: "127.0.0.1:3000",
        Origin: "http://127.0.0.1:3000",
      },
      '{"decision":"REJECTED"}',
    ),
    context,
  );
  expect(response.status).toBe(200);
  expect(response.headers.get("cache-control")).toBe("no-store");
  expect(response.headers.has("set-cookie")).toBe(false);
  expect(response.headers.has("location")).toBe(false);
  const [target, options] = fetch.mock.calls[0];
  expect(target).toBe(`http://127.0.0.1:8000/approvals/${runId}/decision`);
  expect(options).toMatchObject({
    method: "POST",
    headers: {
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
    },
    body: '{"decision":"REJECTED"}',
    redirect: "error",
    cache: "no-store",
  });
  expect(Object.keys(options.headers)).toHaveLength(2);
});

it("rejects foreign origins, missing credentials, arbitrary destinations, paths and oversized bodies before forwarding", async () => {
  vi.stubEnv("RUNVEIL_API_ORIGIN", "http://127.0.0.1:8000");
  const fetch = vi.fn();
  vi.stubGlobal("fetch", fetch);
  expect(
    (await POST(request("POST", { Origin: "http://foreign" }, "{}"), context))
      .status,
  ).toBe(403);
  expect(
    (await POST(new Request(url, { method: "POST" }), context)).status,
  ).toBe(403);
  expect(
    (await GET(request("GET", { Authorization: "" }), context)).status,
  ).toBe(401);
  expect(
    (await GET(request(), { params: Promise.resolve({ runId: "../ready" }) }))
      .status,
  ).toBe(422);
  expect(
    (await POST(request("POST", {}, "x".repeat(2049)), context)).status,
  ).toBe(413);
  vi.stubEnv("RUNVEIL_API_ORIGIN", "http://attacker.example");
  expect((await GET(request(), context)).status).toBe(503);
  expect(
    (await GET(request("GET", { Host: "foreign.example" }), context)).status,
  ).toBe(403);
  expect(fetch).not.toHaveBeenCalled();
});

it("bounds stalled input and upstream bodies and replaces upstream errors with safe errors", async () => {
  vi.stubEnv("RUNVEIL_API_ORIGIN", "http://127.0.0.1:8000");
  const fetch = vi.fn();
  vi.stubGlobal("fetch", fetch);
  fetch.mockResolvedValueOnce(new Response("private error", { status: 409 }));
  const conflict = await GET(request(), context);
  expect(conflict.status).toBe(409);
  expect(await conflict.text()).not.toContain("private");
  fetch.mockResolvedValueOnce(Response.json({ text: "x".repeat(131072) }));
  expect((await GET(request(), context)).status).toBe(502);
  vi.useFakeTimers();
  fetch.mockResolvedValueOnce(
    new Response(new ReadableStream(), {
      headers: { "Content-Type": "application/json" },
    }),
  );
  const pending = GET(request(), context);
  await vi.advanceTimersByTimeAsync(8001);
  expect((await pending).status).toBe(502);
  const calls = fetch.mock.calls.length;
  const incoming = new Request(url, {
    method: "POST",
    headers: request().headers,
    body: new ReadableStream(),
    duplex: "half",
  } as RequestInit & { duplex: "half" });
  const stalled = POST(incoming, context);
  await vi.advanceTimersByTimeAsync(8001);
  expect((await stalled).status).toBe(502);
  expect(fetch.mock.calls.length).toBe(calls);
});
