/**
 * Control-plane Agent Kenny chat client (internal key).
 *
 * The G1.a CP route ships JSON only; SSE-shaped Zod schemas are kept here so
 * the BFF / web can flip to streaming without churning the client surface
 * when G1.b's streaming primitives are wired into the route (follow-up).
 */
import { z } from "zod";

import { getControlPlaneBaseUrl, getControlPlaneInternalKey } from "@/lib/internal/control-plane";

const _UUID = z.string().uuid();

export const zOracleChatRequest = z.object({
  conversation_id: z.string().uuid().nullable(),
  message: z.string().min(1).max(4000),
});
export type OracleChatRequest = z.infer<typeof zOracleChatRequest>;

export const zOracleChatResponse = z.object({
  turn_id: _UUID,
  conversation_id: _UUID,
  content: z.string(),
  tokens_used: z.number().int().nonnegative(),
});
export type OracleChatResponse = z.infer<typeof zOracleChatResponse>;

export const zOracleTurn = z.object({
  id: _UUID,
  conversation_id: _UUID,
  role: z.enum(["user", "oracle"]),
  content: z.string(),
  tokens_used: z.number().int().nonnegative(),
  created_at: z.string(),
});
export type OracleTurn = z.infer<typeof zOracleTurn>;

export const zOracleHistory = z.object({
  conversation_id: z.string().uuid().nullable(),
  turns: z.array(zOracleTurn),
});
export type OracleHistory = z.infer<typeof zOracleHistory>;

// Forward-compat: SSE chunks per the design doc + G1.b stream contract.
// The current CP route returns JSON; once the route flips to text/event-stream
// the BFF proxy parses each frame against these schemas.
export const zOracleSseDelta = z.object({
  delta: z.string(),
  done: z.literal(false),
});
export type OracleSseDelta = z.infer<typeof zOracleSseDelta>;

export const zOracleSseDone = z.object({
  done: z.literal(true),
  turn_id: _UUID,
  conversation_id: _UUID,
  tokens_used: z.number().int().nonnegative(),
});
export type OracleSseDone = z.infer<typeof zOracleSseDone>;

export const zOracleBudgetExhausted = z.object({
  error: z.string(),
  retry_after_iso: z.string(),
});
export type OracleBudgetExhausted = z.infer<typeof zOracleBudgetExhausted>;

export class OracleBudgetExhaustedError extends Error {
  retryAfterIso: string;
  constructor(message: string, retryAfterIso: string) {
    super(message);
    this.name = "OracleBudgetExhaustedError";
    this.retryAfterIso = retryAfterIso;
  }
}

function cpHeaders(actorId: string): Record<string, string> {
  const key = getControlPlaneInternalKey();
  if (!key) {
    throw new Error("DEPLOYAI_INTERNAL_API_KEY not set");
  }
  return {
    "X-DeployAI-Internal-Key": key,
    "X-DeployAI-Actor-Id": actorId,
  };
}

function cpBase(): string {
  const base = getControlPlaneBaseUrl()?.replace(/\/$/, "");
  if (!base) {
    throw new Error("DEPLOYAI_CONTROL_PLANE_URL not set");
  }
  return base;
}

export async function cpPostOracleChat(
  tenantId: string,
  engagementId: string,
  actorId: string,
  body: OracleChatRequest,
): Promise<OracleChatResponse> {
  const url =
    `${cpBase()}/internal/v1/engagements/${encodeURIComponent(engagementId)}/oracle/chat` +
    `?tenant_id=${encodeURIComponent(tenantId)}`;
  const r = await fetch(url, {
    method: "POST",
    headers: { ...cpHeaders(actorId), "Content-Type": "application/json" },
    body: JSON.stringify(body),
    cache: "no-store",
  });
  if (r.status === 429) {
    const raw: unknown = await r.json().catch(() => ({}));
    const parsed = zOracleBudgetExhausted.safeParse(
      // FastAPI nests the structured body under `detail`.
      (raw as { detail?: unknown })?.detail ?? raw,
    );
    if (parsed.success) {
      throw new OracleBudgetExhaustedError(parsed.data.error, parsed.data.retry_after_iso);
    }
    throw new OracleBudgetExhaustedError("daily LLM budget exhausted", "");
  }
  if (!r.ok) {
    throw new Error(`cp oracle chat ${r.status}: ${await r.text()}`);
  }
  const raw: unknown = await r.json();
  return zOracleChatResponse.parse(raw);
}

export type OracleSseFrame = OracleSseDelta | OracleSseDone;

/**
 * Stream the CP oracle chat reply as parsed SSE frames. Returns a fetch
 * Response so the BFF can pipe the body through unchanged when proxying.
 * Surfaces budget exhaustion (429) as `OracleBudgetExhaustedError` so the
 * caller can render the same toast as the JSON path.
 */
export async function cpStreamOracleChat(
  tenantId: string,
  engagementId: string,
  actorId: string,
  body: OracleChatRequest,
): Promise<Response> {
  const url =
    `${cpBase()}/internal/v1/engagements/${encodeURIComponent(engagementId)}/oracle/chat/stream` +
    `?tenant_id=${encodeURIComponent(tenantId)}`;
  const r = await fetch(url, {
    method: "POST",
    headers: {
      ...cpHeaders(actorId),
      "Content-Type": "application/json",
      Accept: "text/event-stream",
    },
    body: JSON.stringify(body),
    cache: "no-store",
  });
  if (r.status === 429) {
    const raw: unknown = await r.json().catch(() => ({}));
    const parsed = zOracleBudgetExhausted.safeParse((raw as { detail?: unknown })?.detail ?? raw);
    if (parsed.success) {
      throw new OracleBudgetExhaustedError(parsed.data.error, parsed.data.retry_after_iso);
    }
    throw new OracleBudgetExhaustedError("daily LLM budget exhausted", "");
  }
  if (!r.ok) {
    throw new Error(`cp oracle chat stream ${r.status}: ${await r.text()}`);
  }
  return r;
}

export async function cpGetOracleHistory(
  tenantId: string,
  engagementId: string,
  actorId: string,
): Promise<OracleHistory> {
  const url =
    `${cpBase()}/internal/v1/engagements/${encodeURIComponent(engagementId)}/oracle/history` +
    `?tenant_id=${encodeURIComponent(tenantId)}`;
  const r = await fetch(url, { method: "GET", headers: cpHeaders(actorId), cache: "no-store" });
  if (!r.ok) {
    throw new Error(`cp oracle history ${r.status}: ${await r.text()}`);
  }
  const raw: unknown = await r.json();
  return zOracleHistory.parse(raw);
}
