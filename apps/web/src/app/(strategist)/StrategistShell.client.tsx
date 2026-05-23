"use client";

import * as React from "react";

import { AppShell } from "@/components/chrome/AppShell";
import { StrategistToaster } from "@/components/chrome/StrategistToaster";

type Props = {
  children: React.ReactNode;
};

/**
 * MVP shell. Stripped down to the bare minimum after the 2026-05-23
 * BMAD cleanup: just the toaster + the app chrome wrapping `/engagements`.
 *
 * The pre-cleanup version polled `/api/internal/strategist-activity`,
 * merged demo-query overrides, threaded a `StrategistSurfaceProvider`
 * for agentDegraded / ingestionInProgress / in-meeting flags, and
 * displayed a freshness chip + locked-phase indicator + global command
 * palette. None of that is part of the MVP product surface — the
 * engagement loop has its own per-page refresh affordances on the
 * insights + matrix sections.
 */
export function StrategistShell({ children }: Props) {
  return (
    <>
      <StrategistToaster />
      <AppShell>{children}</AppShell>
    </>
  );
}
