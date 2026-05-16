/**
 * Opaque correlation identifiers for Web→CP requests (`X-DeployAI-Correlation-Id`).
 * Middleware stamps `x-deployai-correlation-id` on inbound requests; strategist loaders reuse it.
 */

export function pickCorrelationIdFromIncoming(headers: Headers): string | undefined {
  const direct = headers.get("x-deployai-correlation-id")?.trim();
  if (direct) {
    return direct;
  }
  const xr = headers.get("x-request-id")?.trim();
  return xr || undefined;
}

/** Ensures every middleware-handled request carries a correlation id for downstream server code. */
export function ensureRequestCorrelationHeader(target: Headers, incoming: Headers): string {
  const picked = pickCorrelationIdFromIncoming(target) || pickCorrelationIdFromIncoming(incoming);
  const id = picked ?? crypto.randomUUID();
  target.set("x-deployai-correlation-id", id);
  return id;
}

/**
 * One opaque id per strategist-activity CP hop batch: reuse ingress correlation when present,
 * otherwise a random UUID (never derive from user profile / meeting title).
 */
export function resolveStrategistOutboundCorrelationId(inbound?: string | null): string {
  const t = inbound?.trim();
  if (t) {
    return t;
  }
  return crypto.randomUUID();
}
