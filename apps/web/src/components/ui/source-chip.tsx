"use client";

/**
 * SourceChip — Beautiful UI component 03's inline sources.
 *
 * Compact numbered chip rendered inline with streamed/answer text; hovering
 * (or focusing) reveals a popover with the source title, domain, and an
 * optional snippet. `SourcesRow` renders the "N sources" summary strip that
 * sits under an answer.
 *
 * Purely presentational — pass resolved source metadata in; no fetching.
 */

import * as React from "react";

import { HoverCard, HoverCardContent, HoverCardTrigger } from "@/components/ui/hover-card";
import { cn } from "@/lib/utils";

export type SourceChipSource = {
  /** 1-based citation number shown inside the chip. */
  index: number;
  /** Human title of the source document / record. */
  title: string;
  /** Short origin label (domain, system name, doc id). */
  origin?: string;
  /** Optional supporting snippet shown in the popover. */
  snippet?: string;
  /** Optional link target; chip stays a <button> when absent. */
  href?: string;
};

const chipClass =
  "inline-flex h-4 min-w-4 shrink-0 translate-y-[-1px] cursor-default items-center justify-center rounded-full bg-hover-2 px-1 align-middle text-[10px] font-semibold tabular-nums leading-none text-ink-2 shadow-hairline transition-colors hover:bg-accent-tint hover:text-accent-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/50";

function SourceChip({
  source,
  className,
  ...props
}: React.ComponentProps<"button"> & { source: SourceChipSource }) {
  return (
    <HoverCard openDelay={150} closeDelay={100}>
      <HoverCardTrigger asChild>
        <button
          type="button"
          data-slot="source-chip"
          aria-label={`Source ${source.index}: ${source.title}`}
          className={cn(chipClass, className)}
          {...props}
        >
          {source.index}
        </button>
      </HoverCardTrigger>
      <HoverCardContent side="top" align="center" className="w-64 p-3">
        <div className="flex flex-col gap-1">
          <p className="text-sm leading-snug font-medium text-ink">{source.title}</p>
          {source.origin ? (
            <p className="truncate font-mono text-xs text-ink-2">{source.origin}</p>
          ) : null}
          {source.snippet ? (
            <p className="mt-1 line-clamp-3 text-xs leading-relaxed text-ink-2">{source.snippet}</p>
          ) : null}
          {source.href ? (
            <a
              href={source.href}
              target="_blank"
              rel="noreferrer"
              className="mt-1 w-fit text-xs font-medium text-accent-ink underline-offset-2 hover:underline"
            >
              Open source
            </a>
          ) : null}
        </div>
      </HoverCardContent>
    </HoverCard>
  );
}

/** "N sources" strip under an answer — first few origins + counter. */
function SourcesRow({
  sources,
  className,
  ...props
}: React.ComponentProps<"div"> & { sources: SourceChipSource[] }) {
  if (sources.length === 0) return null;
  const shown = sources.slice(0, 3);
  return (
    <div
      data-slot="sources-row"
      className={cn("flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-ink-2", className)}
      {...props}
    >
      <span className="font-medium text-ink">
        {sources.length} source{sources.length === 1 ? "" : "s"}
      </span>
      {shown.map((source) => (
        <span key={source.index} className="inline-flex items-center gap-1.5">
          <SourceChip source={source} />
          <span className="max-w-40 truncate">{source.origin ?? source.title}</span>
        </span>
      ))}
      {sources.length > shown.length ? <span>+{sources.length - shown.length} more</span> : null}
    </div>
  );
}

export { SourceChip, SourcesRow };
