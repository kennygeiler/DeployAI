/**
 * Epic 9 Story 9.1 — strategist activity poll cadence (meeting + ingest signals).
 * AC: configurable polling interval ≤ 30 s (`epics.md` Story 9.1).
 */

const DEFAULT_MS = 30_000;
const MIN_MS = 5_000;
const MAX_MS = 30_000;

/** Pure parse + clamp for unit tests and SSR default path. */
export function strategistActivityPollMsFromEnv(raw: string | undefined | null): number {
  if (raw == null || String(raw).trim() === "") {
    return DEFAULT_MS;
  }
  const n = Number.parseInt(String(raw), 10);
  if (!Number.isFinite(n) || n < MIN_MS) {
    return DEFAULT_MS;
  }
  return Math.min(MAX_MS, n);
}

/**
 * Client-visible poll interval for `GET /api/internal/strategist-activity`.
 * `NEXT_PUBLIC_DEPLOYAI_STRATEGIST_ACTIVITY_POLL_MS` may lower the interval in dev
 * (still clamped to ≤ 30 s for production alignment).
 */
export function getStrategistActivityPollIntervalMs(): number {
  if (typeof window === "undefined") {
    return DEFAULT_MS;
  }
  return strategistActivityPollMsFromEnv(
    process.env.NEXT_PUBLIC_DEPLOYAI_STRATEGIST_ACTIVITY_POLL_MS,
  );
}
