"use client";

import * as React from "react";

export type StrategistSurfaceValue = {
  /** When true, surfaces downgrade agent-backed UI; shell shows `AgentOutageBanner`. */
  agentDegraded: boolean;
  /** Ingestion / extraction in flight (FR47) — top-rail activity. */
  ingestionInProgress: boolean;
  /** Strategist-local calendar day (YYYY-MM-DD) from server BFF for mock due windows. */
  strategistLocalDate: string;
  /** Epic 9.1 — meeting presence from control plane stub or URL demo flags. */
  inMeeting: boolean;
  meetingId: string | null;
  meetingTitle: string | null;
  oracleInMeetingAlertAt: string | null;
  meetingDetectionSource: string | null;
  calendarPollIntervalSeconds: number | null;
};

const defaultValue: StrategistSurfaceValue = {
  agentDegraded: false,
  ingestionInProgress: false,
  strategistLocalDate: "1970-01-01",
  inMeeting: false,
  meetingId: null,
  meetingTitle: null,
  oracleInMeetingAlertAt: null,
  meetingDetectionSource: "off",
  calendarPollIntervalSeconds: null,
};

const StrategistSurfaceContext = React.createContext<StrategistSurfaceValue | null>(null);

export function StrategistSurfaceProvider({
  value,
  children,
}: {
  value: StrategistSurfaceValue;
  children: React.ReactNode;
}) {
  return (
    <StrategistSurfaceContext.Provider value={value}>{children}</StrategistSurfaceContext.Provider>
  );
}

/** Defaults to off when used outside the strategist layout (e.g. Storybook). */
export function useStrategistSurface(): StrategistSurfaceValue {
  return React.useContext(StrategistSurfaceContext) ?? defaultValue;
}
