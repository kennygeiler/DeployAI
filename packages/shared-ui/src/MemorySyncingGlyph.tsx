"use client";

import * as React from "react";
import { CloudOff, RefreshCw } from "lucide-react";

import { cn } from "./lib/utils";

export type MemorySyncingGlyphState = "syncing" | "stale" | "unavailable";

export type MemorySyncingGlyphProps = {
  state: MemorySyncingGlyphState;
  label: string;
  className?: string;
};

/**
 * Small glyph + label for memory sync / exceed-SLO (FR48, UX-DR25). Pairs with `FreshnessChip` thresholds.
 */
export function MemorySyncingGlyph({ state, label, className: classNameProp }: MemorySyncingGlyphProps) {
  const Icon = state === "unavailable" ? CloudOff : RefreshCw;
  return (
    <span
      role="status"
      className={cn(
        "inline-flex items-center gap-1.5 rounded-md border border-border bg-paper-100 px-2 py-0.5 text-xs font-medium text-ink-800",
        state === "stale" && "border-amber-600/30 bg-amber-50/80 text-amber-950",
        state === "unavailable" && "border-border bg-paper-200 text-ink-600",
        classNameProp,
      )}
    >
      <Icon
        className={cn("size-3.5", state === "syncing" && "animate-spin")}
        aria-hidden
      />
      <span>{label}</span>
    </span>
  );
}
