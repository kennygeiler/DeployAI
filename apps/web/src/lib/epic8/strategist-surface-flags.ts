import type { StrategistSurfaceValue } from "./strategist-surface-context";

/**
 * ORs demo query flags onto the server/BFF snapshot so `?agentError=1` survives client refresh
 * polling (Epic 8.7 manual QA without intercepting `/api/internal/strategist-activity`).
 */
export function mergeStrategistSurfaceFromDemoQuery(
  base: StrategistSurfaceValue,
  query: string | Readonly<URLSearchParams> | URLSearchParams,
): StrategistSurfaceValue {
  const q = parseStrategistSurfaceQuery(query);
  return {
    strategistLocalDate: base.strategistLocalDate,
    agentDegraded: base.agentDegraded || q.agentDegraded,
    ingestionInProgress: base.ingestionInProgress || q.ingestionInProgress,
  };
}

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
    /** Query override does not model calendar; URL-driven demos use a fixed stub. */
    strategistLocalDate: "1970-01-01",
  };
}
