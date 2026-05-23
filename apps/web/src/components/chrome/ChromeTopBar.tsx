"use client";

import * as React from "react";
import Link from "next/link";

import { cn } from "@/lib/utils";

export type ChromeTopBarProps = {
  className?: string;
};

/**
 * MVP top bar. Logo only. The pre-cleanup version carried:
 * - a `<PhaseIndicator>` locked to P5_pilot (BMAD phase model)
 * - an `<FreshnessChip>` driven by `lastSyncedAt` polling
 * - an `Ingesting…` chip from the strategist surface context
 * - an `/evidence/...` breadcrumb that linked back to `/digest`
 * - a `⌘K` command-palette trigger
 *
 * None of these are part of the MVP product surface. Removed alongside
 * `lib/epic8`, the activity poller, and the command palette.
 */
export function ChromeTopBar({ className }: ChromeTopBarProps) {
  return (
    <header
      className={cn(
        "bg-background/95 border-border flex h-14 shrink-0 items-center gap-3 border-b px-3 backdrop-blur md:px-4",
        className,
      )}
    >
      <Link
        href="/engagements"
        className="text-ink-900 focus-visible:ring-ring text-sm font-semibold focus-visible:rounded focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-offset-2 xl:hidden"
      >
        DeployAI
      </Link>
    </header>
  );
}
