import { describe, expect, it } from "vitest";

import { nextResponseFromStrategistCpFetchError } from "./strategist-bff-cp-error";

async function readJson(res: ReturnType<typeof nextResponseFromStrategistCpFetchError>) {
  return (await res.json()) as Record<string, unknown>;
}

describe("nextResponseFromStrategistCpFetchError", () => {
  it("maps CP 404 to 404 with userMessage", async () => {
    const res = nextResponseFromStrategistCpFetchError(new Error("cp action-queue patch 404: gone"));
    expect(res.status).toBe(404);
    const j = await readJson(res);
    expect(j.source).toBe("cp_error");
    expect(j.code).toBe("cp_not_found");
  });

  it("maps CP 5xx to 502 degraded without naming internal services", async () => {
    const res = nextResponseFromStrategistCpFetchError(
      new Error("cp validation-queue list 503: timeout"),
    );
    expect(res.status).toBe(502);
    const j = await readJson(res);
    expect(j.code).toBe("cp_5xx");
    expect(String(j.userMessage)).toMatch(/temporarily unreachable/i);
    expect(String(j.userMessage).toLowerCase()).not.toContain("control plane");
  });

  it("maps missing-config style errors to 502 unreachable", async () => {
    const res = nextResponseFromStrategistCpFetchError(new Error("DEPLOYAI_INTERNAL_API_KEY not set"));
    expect(res.status).toBe(502);
    const j = await readJson(res);
    expect(j.code).toBe("cp_unreachable");
  });
});
