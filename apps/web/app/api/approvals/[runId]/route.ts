import { bounded } from "../../../../lib/bounded-body";

const headers = {
  "Cache-Control": "no-store",
  "X-Content-Type-Options": "nosniff",
};

function failure(status: number) {
  return Response.json(
    { error: "approval_request_failed" },
    { status, headers },
  );
}

async function proxy(request: Request, runId: string, deciding: boolean) {
  const origin = request.headers.get("origin");
  // Next may normalize request.url's hostname. Compare against the local HTTP Host,
  // never X-Forwarded-Host; this console does not support a remote reverse proxy.
  const host = request.headers.get("host") ?? new URL(request.url).host;
  if (!/^(127\.0\.0\.1|localhost|\[::1\])(?::[0-9]{1,5})?$/.test(host))
    return failure(403);
  if ((deciding && !origin) || (origin && origin !== `http://${host}`)) {
    return failure(403);
  }
  if (request.headers.get("sec-fetch-site") === "cross-site")
    return failure(403);
  const authorization = request.headers.get("authorization");
  if (!authorization || !/^Bearer [A-Za-z0-9_-]{43,128}$/.test(authorization))
    return failure(401);
  if (!/^[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}$/i.test(runId))
    return failure(422);
  // Explicit local destination only. Neither path nor target comes from a request URL.
  const upstream = process.env.RUNVEIL_API_ORIGIN;
  if (!upstream || !/^http:\/\/127\.0\.0\.1:[0-9]{1,5}$/.test(upstream))
    return failure(503);
  if (
    deciding &&
    request.headers.get("content-type")?.split(";")[0].trim() !==
      "application/json"
  )
    return failure(415);
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 8000);
  try {
    let body: string | undefined;
    if (deciding) {
      try {
        body = await bounded(request.body, 2048, controller.signal);
      } catch (error) {
        if (error instanceof RangeError) return failure(413);
        throw error;
      }
    }
    const response = await fetch(
      `${upstream}/approvals/${runId}${deciding ? "/decision" : ""}`,
      {
        method: deciding ? "POST" : "GET",
        headers: {
          Authorization: authorization,
          "Content-Type": "application/json",
        },
        body,
        cache: "no-store",
        redirect: "error",
        signal: controller.signal,
      },
    );
    if (!response.ok) {
      await response.body?.cancel();
      return failure(
        [401, 404, 409, 413, 415, 422, 503].includes(response.status)
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
    const payload = await bounded(response.body, 131072, controller.signal);
    JSON.parse(payload); // Never relay HTML, headers, cookies or redirect destinations.
    return new Response(payload, {
      headers: { ...headers, "Content-Type": "application/json" },
    });
  } catch {
    return failure(502);
  } finally {
    clearTimeout(timer);
  }
}

type Context = { params: Promise<{ runId: string }> };
export async function GET(request: Request, context: Context) {
  return proxy(request, (await context.params).runId, false);
}
export async function POST(request: Request, context: Context) {
  return proxy(request, (await context.params).runId, true);
}
