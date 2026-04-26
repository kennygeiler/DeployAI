import type { StrategistSurfaceValue } from "./strategist-surface-context";

/**
 * Centralizes dev / preview query parsing for Epic 8.7. Replace with health API in production.
 * Pure: unit-test this without a browser.
 */
export function parseStrategistSurfaceQuery(
  sp: string | Readonly<URLSearchParams> | URLSearchParams,
): StrategistSurfaceValue {
  const p = typeof sp === "string" ? new URLSearchParams(sp) : sp;
  return {
    agentDegraded:
      p.get("agentError") === "1" || p.get("agentDegraded") === "1" || p.get("degraded") === "1",
    ingestionInProgress: p.get("ingest") === "1" || p.get("ingesting") === "1",
  };
}
