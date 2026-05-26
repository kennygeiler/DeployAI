import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const { headersMock, cookiesMock } = vi.hoisted(() => ({
  headersMock: vi.fn(),
  cookiesMock: vi.fn(),
}));

vi.mock("next/headers", () => ({
  headers: () => headersMock(),
  cookies: () => cookiesMock(),
}));

const { cpPostOracleChatMock, OracleBudgetExhaustedErrorMock } = vi.hoisted(() => {
  class _OracleBudgetExhaustedError extends Error {
    retryAfterIso: string;
    constructor(message: string, retryAfterIso: string) {
      super(message);
      this.name = "OracleBudgetExhaustedError";
      this.retryAfterIso = retryAfterIso;
    }
  }
  return {
    cpPostOracleChatMock: vi.fn(),
    OracleBudgetExhaustedErrorMock: _OracleBudgetExhaustedError,
  };
});

vi.mock("@/lib/internal/oracle-cp", async () => {
  const actual = await vi.importActual<typeof import("@/lib/internal/oracle-cp")>(
    "@/lib/internal/oracle-cp",
  );
  return {
    ...actual,
    cpPostOracleChat: cpPostOracleChatMock,
    OracleBudgetExhaustedError: OracleBudgetExhaustedErrorMock,
  };
});

import { POST } from "./route";

const TURN_ID = "00000000-0000-4000-8000-000000000aaa";
const CONVO_ID = "00000000-0000-4000-8000-000000000bbb";
const ACTOR_ID = "00000000-0000-4000-8000-0000000000aa";

function authedHeaders(): Headers {
  return new Headers({
    "x-deployai-role": "fde",
    "x-deployai-tenant": "t1",
    "x-deployai-actor-id": ACTOR_ID,
  });
}

function params() {
  return Promise.resolve({ engagementId: "e1" });
}

function postReq(body: unknown): Request {
  return new Request("http://localhost/api/bff/engagements/e1/oracle/chat", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  });
}

describe("POST /api/bff/engagements/[engagementId]/oracle/chat", () => {
  beforeEach(() => {
    headersMock.mockResolvedValue(authedHeaders());
    cookiesMock.mockResolvedValue({ get: () => undefined });
    vi.stubEnv("DEPLOYAI_CONTROL_PLANE_URL", "http://cp.test");
    vi.stubEnv("DEPLOYAI_INTERNAL_API_KEY", "k");
  });

  afterEach(() => {
    vi.unstubAllEnvs();
    cpPostOracleChatMock.mockReset();
  });

  it("forwards the validated body to CP and returns the JSON reply", async () => {
    cpPostOracleChatMock.mockResolvedValue({
      turn_id: TURN_ID,
      conversation_id: CONVO_ID,
      content: "I see two open risks worth your attention.",
      tokens_used: 412,
    });

    const res = await POST(
      postReq({
        conversation_id: null,
        message: "what should I worry about?",
      }) as unknown as Parameters<typeof POST>[0],
      { params: params() },
    );

    expect(res.status).toBe(200);
    expect(cpPostOracleChatMock).toHaveBeenCalledWith("t1", "e1", ACTOR_ID, {
      conversation_id: null,
      message: "what should I worry about?",
    });
    const body = await res.json();
    expect(body.turn_id).toBe(TURN_ID);
    expect(body.conversation_id).toBe(CONVO_ID);
    expect(body.content).toContain("two open risks");
    expect(body.tokens_used).toBe(412);
    expect(body.source).toBe("cp");
  });

  it("rejects an empty message at the BFF boundary", async () => {
    const res = await POST(
      postReq({ conversation_id: null, message: "" }) as unknown as Parameters<typeof POST>[0],
      { params: params() },
    );
    expect(res.status).toBe(400);
    expect(cpPostOracleChatMock).not.toHaveBeenCalled();
  });

  it("rejects an oversized message (> 4000 chars)", async () => {
    const res = await POST(
      postReq({ conversation_id: null, message: "x".repeat(4001) }) as unknown as Parameters<
        typeof POST
      >[0],
      { params: params() },
    );
    expect(res.status).toBe(400);
    expect(cpPostOracleChatMock).not.toHaveBeenCalled();
  });

  it("returns 400 on invalid JSON body", async () => {
    const req = new Request("http://localhost/api/bff/engagements/e1/oracle/chat", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: "not json",
    });
    const res = await POST(req as unknown as Parameters<typeof POST>[0], { params: params() });
    expect(res.status).toBe(400);
    expect(cpPostOracleChatMock).not.toHaveBeenCalled();
  });

  it("maps a budget-exhausted error to a 429 with a friendly userMessage", async () => {
    cpPostOracleChatMock.mockRejectedValue(
      new OracleBudgetExhaustedErrorMock("daily LLM budget exhausted", "2026-05-26T00:00:00Z"),
    );

    const res = await POST(
      postReq({ conversation_id: null, message: "hi" }) as unknown as Parameters<typeof POST>[0],
      { params: params() },
    );

    expect(res.status).toBe(429);
    const body = await res.json();
    expect(body.code).toBe("oracle_daily_budget");
    expect(body.userMessage).toMatch(/daily llm budget reached/i);
    expect(body.retry_after_iso).toBe("2026-05-26T00:00:00Z");
  });

  it("returns 401 when no actor", async () => {
    headersMock.mockResolvedValue(new Headers());
    const res = await POST(
      postReq({ conversation_id: null, message: "hi" }) as unknown as Parameters<typeof POST>[0],
      { params: params() },
    );
    expect(res.status).toBe(401);
    expect(cpPostOracleChatMock).not.toHaveBeenCalled();
  });
});
