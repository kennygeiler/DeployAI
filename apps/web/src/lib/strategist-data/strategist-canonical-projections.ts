/**
 * Roadmap stubs for durable canonical-memory → strategist surface projections (production data plane).
 * Pilot deployments continue to use CP file-backed pilot surfaces (`DEPLOYAI_PILOT_SURFACE_DATA_PATH`) or HTTP URLs;
 * these types are not wired into loaders and do not change runtime behavior.
 *
 * Opt-in for future experiments only: `DEPLOYAI_STRATEGIST_CANONICAL_PROJECTIONS_STUB=1` (reserved; no prod claims).
 */

/** Surfaces that eventually consume canonical projection rows (aligned with strategist-data-plane §2). */
export type StrategistCanonicalSurface =
  | "morning_digest_top"
  | "evidence_node"
  | "phase_tracking"
  | "evening_synthesis";

/** Tenant-scoped projection cursor for incremental replay (placeholder). */
export type CanonicalProjectionCursor = {
  readonly tenantId: string;
  readonly streamPosition: string;
};

export type CanonicalProjectionJobKind =
  | "batch_emit"
  | "stream_emit";

export type CanonicalProjectionWriteIntent = {
  readonly surface: StrategistCanonicalSurface;
  readonly tenantId: string;
  readonly emittedAtIso: string;
  readonly jobKind: CanonicalProjectionJobKind;
};

export function strategistCanonicalProjectionsStubFlagEnabled(): boolean {
  return process.env.DEPLOYAI_STRATEGIST_CANONICAL_PROJECTIONS_STUB?.trim() === "1";
}
