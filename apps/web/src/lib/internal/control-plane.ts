/**
 * Server-only control-plane base URL + internal API key.
 * Set in private preview: DEPLOYAI_CONTROL_PLANE_URL, DEPLOYAI_INTERNAL_API_KEY
 * (and optionally fall back to NEXT_PUBLIC_CONTROL_PLANE_URL for the base URL in dev).
 */
export function getControlPlaneBaseUrl(): string | null {
  return (
    process.env.DEPLOYAI_CONTROL_PLANE_URL ?? process.env.NEXT_PUBLIC_CONTROL_PLANE_URL ?? null
  );
}

export function getControlPlaneInternalKey(): string | null {
  return process.env.DEPLOYAI_INTERNAL_API_KEY ?? null;
}
