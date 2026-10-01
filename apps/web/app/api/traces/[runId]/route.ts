import { bounded } from "../../../../lib/bounded-body";

const headers = {
  "Cache-Control": "no-store",
  "X-Content-Type-Options": "nosniff",
};
function failure(status: number) {
  return Response.json({ error: "trace_request_failed" }, { status, headers });
}

// This route has no decision method or server-owned credential.
export async function GET(
  request: Request,
  context: { params: Promise<{ runId: string }> },
) {
  const host = request.headers.get("host") ?? new URL(request.url).host;
  const origin = request.headers.get("origin");
  if (
    !/^(127\.0\.0\.1|localhost|\[::1\])(?::[0-9]{1,5})?$/.test(host) ||
    (origin && origin !== `http://${host}`) ||
    request.headers.get("sec-fetch-site") === "cross-site"
  )
    return failure(403);
  const authorization = request.headers.get("authorization");
  if (!authorization || !/^Bearer [A-Za-z0-9_-]{43,128}$/.test(authorization))
    return failure(401);
  const { runId } = await context.params;
  if (!/^[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}$/i.test(runId))
    return failure(422);
  const params = new URL(request.url).searchParams;
  for (const [key, value] of params) {
    if (
      !["limit", "after_sequence", "expected_sequence"].includes(key) ||
      params.getAll(key).length !== 1 ||
      !/^[0-9]{1,10}$/.test(value) ||
      Number(value) > 2147483647
    )
      return failure(422);
  }
  const limit = Number(params.get("limit") ?? 50);
  if (
    limit < 1 ||
    limit > 100 ||
    (Number(params.get("after_sequence")) > 0 &&
      !params.has("expected_sequence"))
  )
    return failure(422);
  const upstream = process.env.RUNVEIL_API_ORIGIN;
  if (!upstream || !/^http:\/\/127\.0\.0\.1:[0-9]{1,5}$/.test(upstream))
    return failure(503);
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 8000);
  try {
    const response = await fetch(`${upstream}/runs/${runId}/trace?${params}`, {
      method: "GET",
      headers: { Authorization: authorization },
      cache: "no-store",
      credentials: "omit",
      redirect: "error",
      signal: controller.signal,
    });
    if (!response.ok) {
      await response.body?.cancel();
      return failure(
        [401, 404, 409, 422, 503].includes(response.status)
          ? response.status
          : 502,
      );
    }
    if (
      response.headers.get("content-type")?.split(";")[0].trim() !==
      "application/json"
    ) {
      await response.body?.cancel();
      return failure(502);
    }
    const body = await bounded(response.body, 524288, controller.signal);
    JSON.parse(body);
    return new Response(body, {
      headers: { ...headers, "Content-Type": "application/json" },
    });
  } catch {
    return failure(502);
  } finally {
    clearTimeout(timer);
  }
}
