import { describe, expect, it } from "vitest";

import { readStrategistBffErrorDescription } from "./read-strategist-bff-error";

describe("readStrategistBffErrorDescription", () => {
  it("prefers userMessage from JSON body", async () => {
    const res = new Response(
      JSON.stringify({ userMessage: "Try again later", code: "cp_5xx", source: "cp_error" }),
      { status: 502 },
    );
    expect(await readStrategistBffErrorDescription(res)).toBe("Try again later");
  });

  it("falls back to plain text", async () => {
    const res = new Response("raw error", { status: 500 });
    expect(await readStrategistBffErrorDescription(res)).toBe("raw error");
  });
});
