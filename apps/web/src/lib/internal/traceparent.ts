/**
 * W3C trace-context (`traceparent`) helpers for Web→CP requests.
 *
 * The control plane extracts this header into its OpenTelemetry server span
 * (services/control-plane, docs/ops/tracing.md). The BFF forwards a valid
 * inbound `traceparent` unchanged; when none exists it mints a new sampled
 * root so a whole agent turn is still stitched together server-side.
 */

const TRACEPARENT_RE = /^00-([0-9a-f]{32})-([0-9a-f]{16})-([0-9a-f]{2})$/;

export function isValidTraceparent(value: string | null | undefined): boolean {
  const m = value ? TRACEPARENT_RE.exec(value.trim()) : null;
  if (!m) {
    return false;
  }
  // All-zero trace-id / parent-id are invalid per the W3C spec.
  return m[1] !== "0".repeat(32) && m[2] !== "0".repeat(16);
}

function randomHex(bytes: number): string {
  const buf = new Uint8Array(bytes);
  crypto.getRandomValues(buf);
  return Array.from(buf, (b) => b.toString(16).padStart(2, "0")).join("");
}

/** New sampled root: version 00, random trace-id + parent-id, flags 01. */
export function generateTraceparent(): string {
  return `00-${randomHex(16)}-${randomHex(8)}-01`;
}

/** Forward a valid inbound `traceparent`, otherwise generate a fresh one. */
export function ensureTraceparent(inbound?: string | null): string {
  const t = inbound?.trim();
  return t && isValidTraceparent(t) ? t : generateTraceparent();
}
