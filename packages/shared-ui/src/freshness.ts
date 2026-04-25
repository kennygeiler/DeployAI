/**
 * NFR5 freshness SLOs (per-surface) drive band thresholds for `FreshnessChip`.
 * `freshMaxMs`: below this = **fresh**; `staleMaxMs`: below this (and ≥ fresh) = **stale**; else **very-stale**.
 */
export const FRESHNESS_NFR5_MS = {
  /** Morning / Evening — Digest latency target. */
  digest: { freshMaxMs: 15 * 60 * 1000, staleMaxMs: 30 * 60 * 1000 },
  /** In-Meeting — ≤ 60 s staleness. */
  in_meeting: { freshMaxMs: 30 * 1000, staleMaxMs: 60 * 1000 },
  /** Phase & Task tracking — ≤ 5 min. */
  phase_tracking: { freshMaxMs: 2.5 * 60 * 1000, staleMaxMs: 5 * 60 * 1000 },
} as const;

export type FreshnessSurface = keyof typeof FRESHNESS_NFR5_MS;

export type FreshnessState = "fresh" | "stale" | "very-stale" | "unavailable";

export type FreshnessThresholdsMs = {
  freshMaxMs: number;
  staleMaxMs: number;
};

/**
 * Map age since last successful memory sync to a visual/semantic freshness band.
 * When `ageMs` is `null` (e.g. no sync yet), state is `unavailable`.
 */
export function freshnessStateForAge(
  ageMs: number | null,
  t: FreshnessThresholdsMs,
): FreshnessState {
  if (ageMs === null) {
    return "unavailable";
  }
  if (!Number.isFinite(ageMs) || ageMs < 0) {
    return "fresh";
  }
  if (ageMs < t.freshMaxMs) {
    return "fresh";
  }
  if (ageMs < t.staleMaxMs) {
    return "stale";
  }
  return "very-stale";
}

/** Human-readable “Ns ago” for the altimeter (compact). */
export function formatSyncAge(ageMs: number | null): string {
  if (ageMs === null) {
    return "—";
  }
  const s = Math.floor(ageMs / 1000);
  if (s < 60) {
    return `${s}s ago`;
  }
  const m = Math.floor(s / 60);
  if (m < 60) {
    return `${m}m ago`;
  }
  const h = Math.floor(m / 60);
  if (h < 48) {
    return `${h}h ago`;
  }
  const d = Math.floor(h / 24);
  return `${d}d ago`;
}
