import { describe, expect, it } from "vitest";

import { parseStrategistSurfaceQuery } from "./strategist-surface-flags";

describe("parseStrategistSurfaceQuery", () => {
  it("defaults to healthy when no params", () => {
    expect(parseStrategistSurfaceQuery("")).toEqual({
      agentDegraded: false,
      ingestionInProgress: false,
      strategistLocalDate: "1970-01-01",
    });
  });

  it("flags agent when any degradation signal is 1", () => {
    expect(parseStrategistSurfaceQuery("?agentError=1")).toMatchObject({ agentDegraded: true });
    expect(parseStrategistSurfaceQuery("?agentDegraded=1")).toMatchObject({ agentDegraded: true });
    expect(parseStrategistSurfaceQuery("?degraded=1")).toMatchObject({ agentDegraded: true });
  });

  it("flags ingestion for ingest=1 or ingesting=1", () => {
    expect(parseStrategistSurfaceQuery("?ingest=1")).toEqual({
      agentDegraded: false,
      ingestionInProgress: true,
      strategistLocalDate: "1970-01-01",
    });
    expect(parseStrategistSurfaceQuery("?ingesting=1")).toEqual({
      agentDegraded: false,
      ingestionInProgress: true,
      strategistLocalDate: "1970-01-01",
    });
  });

  it("combines with URLSearchParams instance", () => {
    const p = new URLSearchParams();
    p.set("agentError", "1");
    p.set("ingest", "1");
    expect(parseStrategistSurfaceQuery(p)).toEqual({
      agentDegraded: true,
      ingestionInProgress: true,
      strategistLocalDate: "1970-01-01",
    });
  });

  it("ignores non-1 values", () => {
    expect(parseStrategistSurfaceQuery("?agentError=true")).toMatchObject({ agentDegraded: false });
  });
});
