/**
 * Naive per-IP rate limiter for `GET /api/auth/demo` (Wave 4S).
 *
 * Known limitation, on purpose: state is a module-level Map, so it only
 * protects a single web instance and resets on every deploy/restart. Good
 * enough to blunt cookie-mint hammering for the wave-1 public demo; NOT a
 * real limiter. Real limiting would live at the edge (Cloudflare) or in
 * Redis if the demo ever runs on more than one instance.
 */

const RATE_LIMIT_WINDOW_MS = 60_000;
const RATE_LIMIT_MAX = 10;

type Bucket = { windowStart: number; count: number };
const buckets = new Map<string, Bucket>();

/** True when this request pushes `ip` over the per-window budget (10/min). */
export function demoRateLimited(ip: string, now = Date.now()): boolean {
  const b = buckets.get(ip);
  if (!b || now - b.windowStart >= RATE_LIMIT_WINDOW_MS) {
    // Opportunistic sweep so the map cannot grow unbounded across windows.
    if (buckets.size > 1000) {
      for (const [k, v] of buckets) {
        if (now - v.windowStart >= RATE_LIMIT_WINDOW_MS) {
          buckets.delete(k);
        }
      }
    }
    buckets.set(ip, { windowStart: now, count: 1 });
    return false;
  }
  b.count += 1;
  return b.count > RATE_LIMIT_MAX;
}

/** Test helper. */
export function resetDemoRateLimiter(): void {
  buckets.clear();
}
