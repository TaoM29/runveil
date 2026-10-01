import { randomBytes, randomUUID } from "node:crypto";
import { afterEach, expect, it, vi } from "vitest";
import { GET } from "../app/api/traces/[runId]/route";
const runId = randomUUID();
const token = randomBytes(32).toString("base64url");
const context = { params: Promise.resolve({ runId }) };
function request(query = "", headers: Record<string, string> = {}) {
  return new Request(`http://localhost:3000/api/traces/${runId}${query}`, {
    headers: {
      Authorization: `Bearer ${token}`,
      Host: "localhost:3000",
      ...headers,
    },
  });
}
afterEach(() => {
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
  vi.useRealTimers();
});
it("forwards only a bounded read with caller auth and validated pagination to the configured local API", async () => {
  vi.stubEnv("RUNVEIL_API_ORIGIN", "http://127.0.0.1:8000");
  const fetch = vi
    .fn()
    .mockResolvedValue(
      Response.json(
        {},
        { headers: { "Set-Cookie": "private", Location: "http://foreign" } },
      ),
    );
  vi.stubGlobal("fetch", fetch);
  const response = await GET(
    request("?limit=50&after_sequence=50&expected_sequence=75", {
      Cookie: "ambient",
      "X-Forwarded-Host": "foreign",
    }),
    context,
  );
  expect(response.status).toBe(200);
  expect(response.headers.get("cache-control")).toBe("no-store");
  expect(response.headers.has("set-cookie")).toBe(false);
  expect(response.headers.has("location")).toBe(false);
  expect(fetch.mock.calls[0]).toEqual([
    `http://127.0.0.1:8000/runs/${runId}/trace?limit=50&after_sequence=50&expected_sequence=75`,
    {
      method: "GET",
      headers: { Authorization: `Bearer ${token}` },
      cache: "no-store",
      credentials: "omit",
      redirect: "error",
      signal: expect.any(AbortSignal),
    },
  ]);
  fetch.mockClear();
  for (const query of [
    "?token=secret",
    "?limit=101",
    "?limit=1&limit=2",
    "?after_sequence=1",
    "?limit=-1",
    "?expected_sequence=2147483648",
  ]) {
    expect((await GET(request(query), context)).status).toBe(422);
  }
  const rejectedHeaders: Record<string, string>[] = [
    { Origin: "http://foreign" },
    { Host: "foreign" },
    { "sec-fetch-site": "cross-site" },
  ];
  for (const headers of rejectedHeaders) {
    expect((await GET(request("", headers), context)).status).toBe(403);
  }
  expect((await GET(request("", { Authorization: "" }), context)).status).toBe(
    401,
  );
  expect(
    (
      await GET(request(), {
        params: Promise.resolve({ runId: "../approvals" }),
      })
    ).status,
  ).toBe(422);
  vi.stubEnv("RUNVEIL_API_ORIGIN", "http://foreign");
  expect((await GET(request(), context)).status).toBe(503);
  expect(fetch).not.toHaveBeenCalled();
});
it("bounds upstream JSON and stalled streams, refuses HTML, and never reflects errors", async () => {
  vi.stubEnv("RUNVEIL_API_ORIGIN", "http://127.0.0.1:8000");
  const fetch = vi.fn();
  vi.stubGlobal("fetch", fetch);
  fetch.mockResolvedValueOnce(
    new Response("private upstream detail", { status: 409 }),
  );
  const conflict = await GET(request(), context);
  expect(conflict.status).toBe(409);
  expect(await conflict.text()).not.toContain("private");
  fetch.mockResolvedValueOnce(new Response("<html>private</html>"));
  expect((await GET(request(), context)).status).toBe(502);
  fetch.mockResolvedValueOnce(Response.json({ text: "x".repeat(524288) }));
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
});
