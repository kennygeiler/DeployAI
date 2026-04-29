import type { StrategistSurfaceValue } from "./strategist-surface-context";

const meetingOff: Pick<
  StrategistSurfaceValue,
  | "inMeeting"
  | "meetingId"
  | "meetingTitle"
  | "oracleInMeetingAlertAt"
  | "meetingDetectionSource"
  | "calendarPollIntervalSeconds"
> = {
  inMeeting: false,
  meetingId: null,
  meetingTitle: null,
  oracleInMeetingAlertAt: null,
  meetingDetectionSource: "off",
  calendarPollIntervalSeconds: null,
};

/**
 * ORs demo query flags onto the server/BFF snapshot so `?agentError=1` survives client refresh
 * polling (Epic 8.7 manual QA without intercepting `/api/internal/strategist-activity`).
 */
export function mergeStrategistSurfaceFromDemoQuery(
  base: StrategistSurfaceValue,
  query: string | Readonly<URLSearchParams> | URLSearchParams,
): StrategistSurfaceValue {
  const q = parseStrategistSurfaceQuery(query);
  const inMeeting = base.inMeeting || q.inMeeting;
  return {
    strategistLocalDate: base.strategistLocalDate,
    agentDegraded: base.agentDegraded || q.agentDegraded,
    ingestionInProgress: base.ingestionInProgress || q.ingestionInProgress,
    pilotMeetingPresenceAwaitingGraph: base.pilotMeetingPresenceAwaitingGraph,
    inMeeting,
    meetingId: inMeeting ? (q.meetingId ?? base.meetingId) : base.meetingId,
    meetingTitle: inMeeting ? (q.meetingTitle ?? base.meetingTitle) : base.meetingTitle,
    oracleInMeetingAlertAt: inMeeting
      ? (q.oracleInMeetingAlertAt ?? base.oracleInMeetingAlertAt)
      : base.oracleInMeetingAlertAt,
    meetingDetectionSource: inMeeting
      ? q.inMeeting
        ? "url_demo"
        : (base.meetingDetectionSource ?? null)
      : "off",
    calendarPollIntervalSeconds: inMeeting
      ? q.inMeeting
        ? 30
        : (base.calendarPollIntervalSeconds ?? null)
      : null,
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
  const inMeeting = p.get("inMeeting") === "1" || p.get("meeting") === "1";
  const meetingTitleParam = p.get("meetingTitle")?.trim();
  const meetingIdParam = p.get("meetingId")?.trim();
  return {
    agentDegraded:
      p.get("agentError") === "1" || p.get("agentDegraded") === "1" || p.get("degraded") === "1",
    ingestionInProgress: p.get("ingest") === "1" || p.get("ingesting") === "1",
    pilotMeetingPresenceAwaitingGraph: false,
    /** Query override does not model calendar; URL-driven demos use a fixed stub. */
    strategistLocalDate: "1970-01-01",
    ...(inMeeting
      ? {
          inMeeting: true,
          meetingId: meetingIdParam || "demo-meeting",
          meetingTitle: meetingTitleParam || "Demo meeting (URL flag)",
          oracleInMeetingAlertAt: new Date().toISOString(),
          meetingDetectionSource: "url_demo",
          calendarPollIntervalSeconds: 30,
        }
      : meetingOff),
  };
}
