import { describe, expect, it } from "vitest";
import { GET } from "../app/health/route";

describe("web liveness", () => {
  it("returns the service contract without caching", async () => {
    const response = GET();
    expect(response.status).toBe(200);
    expect(response.headers.get("cache-control")).toBe("no-store");
    expect(await response.json()).toEqual({ status: "ok", service: "web" });
  });
});
