"use client";

import * as React from "react";
import { cva } from "class-variance-authority";
import { Activity, AlertTriangle, CloudOff, Radio } from "lucide-react";

import { cn } from "./lib/utils";
import {
  FRESHNESS_NFR5_MS,
  type FreshnessState,
  type FreshnessSurface,
  type FreshnessThresholdsMs,
  formatSyncAge,
  freshnessStateForAge,
} from "./freshness";

const chip = cva(
  "inline-flex h-6 min-w-0 max-w-full items-center justify-center gap-1 rounded-md border px-2 font-sans text-xs font-medium",
  {
    variants: {
      state: {
        fresh: "border-evidence-700/30 bg-evidence-50 text-evidence-700",
        stale: "border-amber-600/40 bg-amber-50/90 text-amber-950",
        "very-stale": "border-border bg-paper-200 text-ink-800",
        unavailable: "border-dashed border-ink-300/60 bg-paper-100 text-ink-500",
      },
    },
    defaultVariants: { state: "unavailable" },
  },
);

function usePrefersReducedMotion(): boolean {
  return React.useSyncExternalStore(
    (onStoreChange) => {
      if (typeof window === "undefined" || !window.matchMedia) {
        return () => {};
      }
      const mq = window.matchMedia("(prefers-reduced-motion: reduce)");
      mq.addEventListener("change", onStoreChange);
      return () => mq.removeEventListener("change", onStoreChange);
    },
    () =>
      typeof window !== "undefined" && window.matchMedia
        ? window.matchMedia("(prefers-reduced-motion: reduce)").matches
        : false,
    () => false,
  );
}

function stateGlyph(s: FreshnessState) {
  if (s === "unavailable") {
    return <CloudOff className="size-3.5 shrink-0" aria-hidden />;
  }
  if (s === "very-stale") {
    return <AlertTriangle className="size-3.5 shrink-0" aria-hidden />;
  }
  if (s === "stale") {
    return <Activity className="size-3.5 shrink-0" aria-hidden />;
  }
  return <Radio className="size-3.5 shrink-0" aria-hidden />;
}

export type FreshnessChipProps = {
  /**
   * Epoch ms of last successful memory sync, or `null` if never / unknown.
   * The chip re-renders on an interval to keep “Ns ago” current.
   */
  lastSyncedAt: number | null;
  /**
   * Use built-in NFR5 bands, or pass explicit millisecond bands (e.g. tests).
   * @default "digest"
   */
  surface?: FreshnessSurface;
  /** Overrides `surface` presets when set. */
  thresholdsMs?: FreshnessThresholdsMs;
  className?: string;
  id?: string;
  /** @default 5000 */
  tickMs?: number;
};

/**
 * Top-right “memory synced Ns ago” altimeter (UX-DR7, NFR5). Not color-only: glyph + text.
 * Honors `prefers-reduced-motion` for CSS transitions.
 */
export function FreshnessChip({
  lastSyncedAt,
  surface = "digest",
  thresholdsMs: thresholdsProp,
  className: classNameProp,
  id: idProp,
  tickMs = 5000,
}: FreshnessChipProps) {
  const [now, setNow] = React.useState(() => Date.now());
  const reduce = usePrefersReducedMotion();

  React.useEffect(() => {
    setNow(Date.now());
    const id = window.setInterval(() => {
      setNow(Date.now());
    }, tickMs);
    return () => window.clearInterval(id);
  }, [tickMs]);

  const thresholds: FreshnessThresholdsMs = thresholdsProp ?? FRESHNESS_NFR5_MS[surface];
  const ageMs: number | null =
    lastSyncedAt === null
      ? null
      : Math.max(0, now - (typeof lastSyncedAt === "number" ? lastSyncedAt : Number(lastSyncedAt)));

  const state: FreshnessState = freshnessStateForAge(ageMs, thresholds);
  const label = formatSyncAge(ageMs);
  const motionClass = reduce ? "" : "transition-colors duration-200";
  const aria = state === "unavailable" ? "Memory sync unavailable" : `Last memory sync ${label}`;

  return (
    <div
      id={idProp}
      className={cn(
        chip({ state }),
        motionClass,
        "outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2",
        classNameProp,
      )}
      role="status"
      aria-label={aria}
      data-freshness={state}
      title={state === "unavailable" ? "No memory sync timestamp" : `Last sync ${label}`}
    >
      {stateGlyph(state)}
      <span className="min-w-0 tabular-nums" aria-hidden>
        {state === "unavailable" ? "Unavailable" : `Synced ${label}`}
      </span>
    </div>
  );
}
