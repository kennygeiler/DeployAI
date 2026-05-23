"use client";

import * as React from "react";

import { ChromeTopBar } from "./ChromeTopBar";
import { StrategistNav } from "./StrategistNav";

export type AppShellProps = {
  children: React.ReactNode;
};

/**
 * MVP shell wrapping `/engagements`. The pre-cleanup version showed
 * agent-outage / pilot-meeting / session banners and rendered a global
 * `StrategistCommandPalette` — all driven by BMAD-era surface flags.
 * Removed entirely along with `lib/epic8`. Per-page surfaces (insights
 * + matrix) carry their own refresh affordances; no global chrome
 * widget is needed for the MVP loop.
 */
export function AppShell({ children }: AppShellProps) {
  return (
    <div className="bg-background flex min-h-screen flex-col text-foreground">
      <div className="flex min-h-0 min-w-0 flex-1">
        <StrategistNav />
        <div className="flex min-w-0 flex-1 flex-col">
          <ChromeTopBar />
          <div className="mx-auto w-full min-w-0 max-w-[1600px] flex-1 px-4 py-6 md:px-6">
            {children}
          </div>
        </div>
      </div>
    </div>
  );
}
