/**
 * Best-effort control plane HTTP helpers for strategist BFF (no app imports here).
 */

export async function fetchControlPlaneHealthzOk(
  controlPlaneBase: string,
  timeoutMs = 5000,
): Promise<boolean> {
  const base = controlPlaneBase.replace(/\/$/, "");
  const url = `${base}/healthz`;
  try {
    const r = await fetch(url, {
      method: "GET",
      cache: "no-store",
      signal: AbortSignal.timeout(timeoutMs),
    });
    if (!r.ok) {
      return false;
    }
    const j = (await r.json()) as { status?: string };
    return j.status === "ok";
  } catch {
    return false;
  }
}

/**
 * `DEPLOYAI_ORACLE_HEALTH_URL` — full URL (e.g. `http://oracle:8080/healthz`).
 * When unset, the agent service is not checked (returns null = unconfigured).
 */
export async function fetchOptionalOracleServiceHealth(
  fullUrl: string | undefined,
  timeoutMs = 5000,
): Promise<boolean | null> {
  const u = fullUrl?.trim();
  if (!u) {
    return null;
  }
  try {
    const r = await fetch(u, {
      method: "GET",
      cache: "no-store",
      signal: AbortSignal.timeout(timeoutMs),
    });
    return r.ok;
  } catch {
    return false;
  }
}
