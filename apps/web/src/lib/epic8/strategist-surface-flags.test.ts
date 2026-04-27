import { describe, expect, it } from "vitest";

import {
  mergeStrategistSurfaceFromDemoQuery,
  parseStrategistSurfaceQuery,
} from "./strategist-surface-flags";

const idleMeeting = {
  inMeeting: false,
  meetingId: null,
  meetingTitle: null,
  oracleInMeetingAlertAt: null,
} as const;

describe("parseStrategistSurfaceQuery", () => {
  it("defaults to healthy when no params", () => {
    expect(parseStrategistSurfaceQuery("")).toEqual({
      agentDegraded: false,
      ingestionInProgress: false,
      strategistLocalDate: "1970-01-01",
      ...idleMeeting,
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
      ...idleMeeting,
    });
    expect(parseStrategistSurfaceQuery("?ingesting=1")).toEqual({
      agentDegraded: false,
      ingestionInProgress: true,
      strategistLocalDate: "1970-01-01",
      ...idleMeeting,
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
      ...idleMeeting,
    });
  });

  it("ignores non-1 values", () => {
    expect(parseStrategistSurfaceQuery("?agentError=true")).toMatchObject({ agentDegraded: false });
  });

  it("flags inMeeting for inMeeting=1", () => {
    const r = parseStrategistSurfaceQuery("?inMeeting=1");
    expect(r.inMeeting).toBe(true);
    expect(r.meetingId).toBe("demo-meeting");
    expect(r.meetingTitle).toBe("Demo meeting (URL flag)");
    expect(r.oracleInMeetingAlertAt).toEqual(expect.any(String));
  });
});

describe("mergeStrategistSurfaceFromDemoQuery", () => {
  const baseHealthy = {
    agentDegraded: false,
    ingestionInProgress: false,
    strategistLocalDate: "2026-04-28",
    ...idleMeeting,
  };

  it("keeps server flags when query is empty", () => {
    expect(mergeStrategistSurfaceFromDemoQuery(baseHealthy, "")).toEqual(baseHealthy);
  });

  it("ORs demo agent degradation onto healthy server snapshot", () => {
    expect(mergeStrategistSurfaceFromDemoQuery(baseHealthy, "?agentError=1")).toEqual({
      ...baseHealthy,
      agentDegraded: true,
    });
  });

  it("ORs demo ingestion onto server snapshot", () => {
    expect(mergeStrategistSurfaceFromDemoQuery(baseHealthy, "?ingest=1")).toEqual({
      ...baseHealthy,
      ingestionInProgress: true,
    });
  });

  it("preserves server degradation when query is healthy", () => {
    const degraded = { ...baseHealthy, agentDegraded: true };
    expect(mergeStrategistSurfaceFromDemoQuery(degraded, "")).toEqual(degraded);
  });

  it("ORs demo inMeeting onto server snapshot", () => {
    const merged = mergeStrategistSurfaceFromDemoQuery(baseHealthy, "?inMeeting=1");
    expect(merged.inMeeting).toBe(true);
    expect(merged.meetingTitle).toBeTruthy();
  });
});
