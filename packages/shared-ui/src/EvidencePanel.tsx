"use client";

import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import type { EvidenceSpan, RetrievalPhase } from "@deployai/contracts";
import { AlertTriangle, Ban, Loader2 } from "lucide-react";

import { cn } from "./lib/utils";

const panelRoot = cva(
  "w-full max-w-[680px] border border-border bg-card text-card-foreground shadow-sm",
  {
    variants: {
      variant: {
        default: "rounded-md p-6",
        standalone: "rounded-md p-6",
        compact: "rounded-sm p-4 text-sm",
      },
    },
    defaultVariants: { variant: "default" },
  },
);

export type EvidencePanelState = "loading" | "loaded" | "degraded" | "tombstoned";

export type SupersessionLabel = "current" | "superseded" | "unknown" | "tombstoned";

export type EvidencePanelMetadata = {
  sourceType: string;
  /** Human-readable timestamp (ISO or localized). */
  timestamp: string;
  /** Deployment phase or product phase label. */
  phase: string;
  /** Retrieval / model confidence, e.g. "0.94" */
  confidence: string;
  /** Whether this node was superseded, tombstoned, or current. */
  supersession: SupersessionLabel;
  /** When `supersession` is `superseded`, optional short note. */
  supersessionDetail?: string;
};

export type EvidencePanelProps = {
  id?: string;
  /** Shown in metadata; aligns with `retrieval_phase` in the citation envelope. */
  retrievalPhase: RetrievalPhase;
  metadata: EvidencePanelMetadata;
  state: EvidencePanelState;
  /**
   * Full evidence body. When `state` is `loaded` or `degraded`, `evidenceSpan` highlights
   * a substring (UTF-16 indices, same as citation envelope `evidence_span`).
   */
  bodyText?: string;
  evidenceSpan?: EvidenceSpan;
  /**
   * Custom body (e.g. `React.lazy` + `Suspense`). Takes precedence over `bodyText` when set.
   */
  children?: React.ReactNode;
  /** Shown in degraded state in addition to partial `bodyText`. */
  degradedHint?: string;
  /** Tombstoned: plain-language reason until Story 7-8 `TombstoneCard` exists. */
  tombstoneMessage?: string;
  /**
   * When the panel is shown (e.g. citation chip expanded), drives polite announcements.
   * @default true
   */
  visible?: boolean;
  className?: string;
} & VariantProps<typeof panelRoot>;

const supersessionText = (m: EvidencePanelMetadata): string => {
  switch (m.supersession) {
    case "current":
      return "Current";
    case "superseded":
      return m.supersessionDetail ? `Superseded — ${m.supersessionDetail}` : "Superseded";
    case "tombstoned":
      return "Removed";
    case "unknown":
    default:
      return "Unknown";
  }
};

/** Renders `body` with one `<mark>` over [start, end) per evidence_span (UX-DR5). */
export function renderHighlightedBody(body: string, span: EvidenceSpan): React.ReactNode {
  const start = Math.max(0, Math.min(body.length, span.start));
  const end = Math.max(start, Math.min(body.length, span.end));
  if (end <= start) {
    return body;
  }
  return (
    <>
      {start > 0 ? body.slice(0, start) : null}
      <mark className="bg-evidence-100 px-0.5 font-medium text-ink-800">
        {body.slice(start, end)}
      </mark>
      {end < body.length ? body.slice(end) : null}
    </>
  );
}

/**
 * Inline evidence region for citation expansion (UX-DR5, FR41). Composes with
 * `CitationChip` — parent controls visibility; this component handles article landmark,
 * metadata row, optional `<mark>` highlights, loading/degraded/tombstoned, and
 * `aria-live` announcements.
 */
export function EvidencePanel({
  id,
  retrievalPhase,
  metadata,
  state,
  bodyText = "",
  evidenceSpan,
  children,
  degradedHint = "Content still syncing. Showing what we have so far.",
  tombstoneMessage = "This evidence is no longer available in canonical memory.",
  visible = true,
  className: classNameProp,
  variant = "default",
}: EvidencePanelProps) {
  const baseId = React.useId();
  const titleId = id ? `${id}-title` : `${baseId}-title`;
  const liveId = id ? `${id}-live` : `${baseId}-live`;

  const [live, setLive] = React.useState("");

  React.useEffect(() => {
    if (!visible) {
      setLive("");
      return;
    }
    if (state === "loading") {
      setLive("Loading evidence.");
      return;
    }
    if (state === "tombstoned") {
      setLive("Evidence removed.");
      return;
    }
    if (state === "degraded") {
      setLive("Partial evidence. Content may still be syncing.");
      return;
    }
    setLive("Evidence expanded.");
  }, [visible, state]);

  return (
    <article
      className={cn(panelRoot({ variant }), classNameProp)}
      aria-labelledby={titleId}
      aria-busy={state === "loading"}
      data-evidence-panel
      data-state={state}
    >
      <div id={liveId} aria-live="polite" aria-atomic="true" className="sr-only">
        {live}
      </div>

      <header className="mb-4 border-b border-border pb-3 font-sans">
        <h2 id={titleId} className="text-base font-semibold text-foreground">
          Evidence
        </h2>
        <p className="mt-0.5 text-xs text-muted-foreground">retrieval_phase: {retrievalPhase}</p>
        <dl className="mt-2 grid grid-cols-[minmax(0,7rem)_1fr] gap-x-2 gap-y-1 text-xs">
          <dt className="text-muted-foreground">Source</dt>
          <dd className="min-w-0 break-words text-ink-800">{metadata.sourceType}</dd>
          <dt className="text-muted-foreground">Timestamp</dt>
          <dd className="min-w-0 break-words text-ink-800">{metadata.timestamp}</dd>
          <dt className="text-muted-foreground">Phase</dt>
          <dd className="min-w-0 break-words text-ink-800">{metadata.phase}</dd>
          <dt className="text-muted-foreground">Confidence</dt>
          <dd className="min-w-0 break-words text-ink-800">{metadata.confidence}</dd>
          <dt className="text-muted-foreground">Supersession</dt>
          <dd className="min-w-0 break-words text-ink-800">{supersessionText(metadata)}</dd>
        </dl>
      </header>

      {state === "loading" ? (
        <div
          className="flex items-center gap-2 font-sans text-sm text-muted-foreground"
          role="status"
        >
          <Loader2 className="size-4 shrink-0 animate-spin" aria-hidden />
          Loading from memory…
        </div>
      ) : null}

      {state === "tombstoned" ? (
        <div
          className="flex items-start gap-2 rounded-md border border-border bg-paper-200 p-3 font-sans text-sm"
          role="status"
        >
          <Ban className="mt-0.5 size-4 shrink-0 text-ink-600" aria-hidden />
          <p className="text-ink-800">{tombstoneMessage}</p>
        </div>
      ) : null}

      {state === "degraded" ? (
        <div className="space-y-2">
          {bodyText ? (
            <p className="whitespace-pre-wrap font-sans text-sm leading-relaxed text-ink-800">
              {evidenceSpan ? renderHighlightedBody(bodyText, evidenceSpan) : bodyText}
            </p>
          ) : null}
          <p className="inline-flex items-center gap-1.5 rounded-md border border-signal-700/30 bg-signal-100 px-2 py-1 text-xs text-signal-700">
            <AlertTriangle className="size-3.5 shrink-0" aria-hidden />
            {degradedHint}
          </p>
        </div>
      ) : null}

      {state === "loaded" ? (
        <div className="font-sans text-sm leading-relaxed tracking-normal">
          {children != null && children !== false ? (
            children
          ) : (
            <p className="whitespace-pre-wrap text-ink-800">
              {evidenceSpan ? renderHighlightedBody(bodyText, evidenceSpan) : bodyText}
            </p>
          )}
        </div>
      ) : null}
    </article>
  );
}
