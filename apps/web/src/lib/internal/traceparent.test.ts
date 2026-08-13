import { afterEach, describe, expect, it, vi } from "vitest";

import { cpStreamOracleChatV2 } from "@/lib/internal/oracle-cp";
import {
  ensureTraceparent,
  generateTraceparent,
  isValidTraceparent,
} from "@/lib/internal/traceparent";

const VALID = "00-0af7651916cd43dd8448eb211c80319c-b7ad6b7169203331-01";

describe("traceparent helpers", () => {
  it("accepts a well-formed traceparent", () => {
    expect(isValidTraceparent(VALID)).toBe(true);
  });

  it("rejects malformed, all-zero, and empty values", () => {
    expect(isValidTraceparent(undefined)).toBe(false);
    expect(isValidTraceparent("")).toBe(false);
    expect(isValidTraceparent("not-a-traceparent")).toBe(false);
    expect(isValidTraceparent(`00-${"0".repeat(32)}-b7ad6b7169203331-01`)).toBe(false);
    expect(isValidTraceparent(`00-0af7651916cd43dd8448eb211c80319c-${"0".repeat(16)}-01`)).toBe(
      false,
    );
  });

  it("generates a valid sampled traceparent", () => {
    const generated = generateTraceparent();
    expect(isValidTraceparent(generated)).toBe(true);
    expect(generated.endsWith("-01")).toBe(true);
  });

  it("forwards a valid inbound value and regenerates otherwise", () => {
    expect(ensureTraceparent(VALID)).toBe(VALID);
    const minted = ensureTraceparent("garbage");
    expect(minted).not.toBe("garbage");
    expect(isValidTraceparent(minted)).toBe(true);
  });
});

describe("cpStreamOracleChatV2 traceparent header", () => {
  afterEach(() => {
    vi.unstubAllEnvs();
    vi.unstubAllGlobals();
  });

  function stubCpFetch() {
    const fetchMock = vi.fn();
    fetchMock.mockResolvedValue({ ok: true, status: 200, body: {} });
    vi.stubGlobal("fetch", fetchMock);
    vi.stubEnv("DEPLOYAI_CONTROL_PLANE_URL", "http://cp.test");
    vi.stubEnv("DEPLOYAI_INTERNAL_API_KEY", "k");
    return fetchMock;
  }

  it("forwards the caller-supplied traceparent to the CP request", async () => {
    const fetchMock = stubCpFetch();
    await cpStreamOracleChatV2(
      "tenant-1",
      "engagement-1",
      "actor-1",
      { conversation_id: null, message: "hi" },
      VALID,
    );
    const init = fetchMock.mock.calls[0]?.[1] as RequestInit;
    expect((init.headers as Record<string, string>).traceparent).toBe(VALID);
  });

  it("mints a valid traceparent when none is supplied", async () => {
    const fetchMock = stubCpFetch();
    await cpStreamOracleChatV2("tenant-1", "engagement-1", "actor-1", {
      conversation_id: null,
      message: "hi",
    });
    const init = fetchMock.mock.calls[0]?.[1] as RequestInit;
    expect(isValidTraceparent((init.headers as Record<string, string>).traceparent)).toBe(true);
  });
});
