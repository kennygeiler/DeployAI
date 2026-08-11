"use client";

/**
 * Loading primitives — Beautiful UI component 01.
 *
 * `Shimmer` is a hairline-ringed block with an animated gradient sweep, for
 * skeleton layouts (`loading.tsx`, suspense fallbacks). `PixelLoader` is the
 * pixel-grid loader with a status label and an elapsed-time counter, for
 * in-flight agent work.
 *
 * Purely presentational; animation keyframes live in `globals.css`
 * (`bui-shimmer`, `bui-pixel-pulse`) and respect `prefers-reduced-motion`.
 */

import * as React from "react";

import { cn } from "@/lib/utils";

function Shimmer({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="shimmer"
      aria-hidden="true"
      className={cn("bui-shimmer h-4 w-full rounded-md", className)}
      {...props}
    />
  );
}

/** Stacked shimmer lines — quick skeleton for a text block. */
function ShimmerLines({
  lines = 3,
  className,
  ...props
}: React.ComponentProps<"div"> & { lines?: number }) {
  return (
    <div data-slot="shimmer-lines" className={cn("space-y-2", className)} {...props}>
      {Array.from({ length: lines }, (_, i) => (
        <Shimmer key={i} className={cn("h-3.5", i === lines - 1 ? "w-3/5" : "w-full")} />
      ))}
    </div>
  );
}

/** 3×3 pixel-grid staggered so the pulse sweeps diagonally. */
const PIXEL_DELAYS = [0, 0.12, 0.24, 0.12, 0.24, 0.36, 0.24, 0.36, 0.48];

function useElapsedSeconds(active: boolean): string {
  const [elapsed, setElapsed] = React.useState(0);

  React.useEffect(() => {
    if (!active) return undefined;
    const startedAt = Date.now();
    const id = setInterval(() => {
      setElapsed((Date.now() - startedAt) / 1000);
    }, 100);
    return () => clearInterval(id);
  }, [active]);

  return elapsed < 60
    ? `${elapsed.toFixed(1)}s`
    : `${Math.floor(elapsed / 60)}m ${Math.round(elapsed % 60)}s`;
}

/**
 * Pixel-grid loader with label + elapsed time ("Churning · 0.9s").
 *
 * @param label   Status verb shown beside the grid (default "Working").
 * @param showElapsed  Render the live elapsed-time counter (default true).
 */
function PixelLoader({
  label = "Working",
  showElapsed = true,
  className,
  ...props
}: React.ComponentProps<"div"> & { label?: string; showElapsed?: boolean }) {
  const elapsed = useElapsedSeconds(showElapsed);

  return (
    <div
      data-slot="pixel-loader"
      role="status"
      className={cn("inline-flex items-center gap-2.5 text-sm text-ink-2", className)}
      {...props}
    >
      <span aria-hidden="true" className="grid grid-cols-3 gap-[2px]">
        {PIXEL_DELAYS.map((delay, i) => (
          <span
            key={i}
            className="bui-pixel size-[3px] rounded-[1px] bg-ink-2"
            style={{ animationDelay: `${delay}s` }}
          />
        ))}
      </span>
      <span className="font-medium">
        {label}
        <span className="sr-only"> — in progress</span>
      </span>
      {/* Counter uses ink-2, not ink-3: it is visible informative text, so it
          must meet AA contrast (axe checks visible text despite aria-hidden). */}
      {showElapsed ? (
        <span aria-hidden="true" className="text-xs tabular-nums text-ink-2">
          {elapsed}
        </span>
      ) : null}
    </div>
  );
}

export { Shimmer, ShimmerLines, PixelLoader };
