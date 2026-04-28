"use client";

import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { Ban, Link2, Pencil, Quote, ScrollText, Sparkles } from "lucide-react";

import { cn } from "./lib/utils";
import {
  ContextMenu,
  ContextMenuContent,
  ContextMenuItem,
  ContextMenuSeparator,
  ContextMenuTrigger,
} from "./components/ui/context-menu";
import { HoverCard, HoverCardContent, HoverCardTrigger } from "./components/ui/hover-card";

const chipRoot = cva(
  "inline-flex max-w-full min-w-0 items-center justify-center gap-1.5 rounded-md border font-mono text-sm font-medium transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring aria-disabled:pointer-events-none aria-disabled:opacity-60",
  {
    variants: {
      visual: {
        default: "border-evidence-700/25 bg-paper-100 text-evidence-700 hover:bg-evidence-100",
        expanded:
          "border-evidence-700/40 bg-paper-100 text-evidence-700 ring-2 ring-ring/40 hover:bg-evidence-100",
        overridden:
          "border-border bg-muted/60 text-ink-600 line-through decoration-2 decoration-ink-600/40",
        tombstoned:
          "border-border bg-paper-200 text-ink-600 line-through decoration-2 decoration-ink-600/40",
      },
      density: {
        inline: "h-6 px-3",
        standalone: "h-6 px-3",
        compact: "h-5 px-2 text-xs",
      },
    },
    defaultVariants: {
      visual: "default",
      density: "inline",
    },
  },
);

export type CitationChipDensity = NonNullable<VariantProps<typeof chipRoot>["density"]>;

export type CitationVisualState = "default" | "overridden" | "tombstoned";

export type CitationPreview = {
  citationId: string;
  retrievalPhase: string;
  confidence: string;
  signedTimestamp: string;
};

export type CitationChipProps = {
  /** Short human label — never a raw UUID. */
  label: string;
  /** Expanded inline (EvidencePanel is composed by the parent; chip stays visible). */
  expanded: boolean;
  onToggleExpand: () => void;
  /** Distinct from hover/focus — drives glyph + long text for UX-DR28. */
  visualState?: CitationVisualState;
  variant?: CitationChipDensity;
  /** HoverCard dwell preview (≥ 250 ms via HoverCard default). */
  preview: CitationPreview;
  onViewEvidence: () => void;
  onOverride: () => void;
  onCopyLink: () => void;
  onCiteInOverride: () => void;
  className?: string;
  id?: string;
  /** If true, primary toggle does not fire (e.g. fully inert chip — rare). */
  disableExpand?: boolean;
  /** Epic 10.3 — deep-link to override / evidence surface (badge becomes navigable). */
  overrideEvidenceHref?: string;
  onOverrideEvidenceNavigate?: () => void;
  /** Epic 10.4 / UX-DR28 — trust earn-back micro-label (parent applies ~30d TTL). */
  trustRecoveryVisible?: boolean;
};

function statusBadge(
  visual: CitationVisualState,
  overrideLink?: { href: string; onNavigate?: () => void },
) {
  if (visual === "overridden") {
    const cls =
      "inline-flex shrink-0 items-center gap-0.5 rounded border border-border bg-paper-100 px-1 py-0 text-[0.65rem] font-sans font-normal text-ink-800";
    const inner = (
      <>
        <Pencil className="size-2.5 shrink-0" aria-hidden />
        Override
      </>
    );
    if (overrideLink?.href) {
      return (
        <a
          href={overrideLink.href}
          className={cn(cls, "no-underline hover:bg-paper-200")}
          data-citation-state-badge="overridden"
          data-citation-override-link="true"
          aria-label="View override evidence"
          onClick={(e) => {
            e.stopPropagation();
            overrideLink.onNavigate?.();
          }}
        >
          {inner}
        </a>
      );
    }
    return (
      <span className={cls} data-citation-state-badge="overridden">
        {inner}
      </span>
    );
  }
  if (visual === "tombstoned") {
    return (
      <span
        className="inline-flex shrink-0 items-center gap-0.5 rounded border border-border bg-paper-200 px-1 py-0 text-[0.65rem] font-sans font-normal text-ink-800 no-underline"
        data-citation-state-badge="tombstoned"
      >
        <Ban className="size-2.5 shrink-0" aria-hidden />
        Removed
      </span>
    );
  }
  return null;
}

/**
 * Signature citation primitive (UX-DR4, FR41/FR43). Hover preview and context
 * menu match the spec; inline evidence expands via a parent `EvidencePanel`
 * (Story 7-2) controlled by `expanded` / `onToggleExpand`.
 */
export function CitationChip({
  label,
  expanded,
  onToggleExpand,
  visualState = "default",
  variant = "inline",
  preview,
  onViewEvidence,
  onOverride,
  onCopyLink,
  onCiteInOverride,
  className,
  id,
  disableExpand = false,
  overrideEvidenceHref,
  onOverrideEvidenceNavigate,
  trustRecoveryVisible = false,
}: CitationChipProps) {
  const visual =
    visualState === "overridden"
      ? "overridden"
      : visualState === "tombstoned"
        ? "tombstoned"
        : expanded
          ? "expanded"
          : "default";

  const ariaLabel = [
    label,
    `Citation ${preview.citationId}`,
    `Phase ${preview.retrievalPhase}`,
    `Confidence ${preview.confidence}`,
    `Timestamp ${preview.signedTimestamp}`,
    visualState === "tombstoned" ? "Removed from memory" : "",
    visualState === "overridden" ? "Superseded by override" : "",
  ]
    .filter(Boolean)
    .join(". ");

  return (
    <HoverCard openDelay={250}>
      <ContextMenu>
        <ContextMenuTrigger asChild>
          <HoverCardTrigger asChild>
            <button
              type="button"
              id={id}
              data-citation-chip
              data-citation-state={visualState}
              data-citation-expanded={expanded ? "true" : "false"}
              data-citation-density={variant}
              aria-expanded={expanded}
              aria-label={ariaLabel}
              aria-disabled={disableExpand}
              className={cn(chipRoot({ visual, density: variant }), className)}
              onClick={() => {
                if (!disableExpand) onToggleExpand();
              }}
              onKeyDown={(e) => {
                if (e.key === "Escape" && expanded) {
                  e.preventDefault();
                  onToggleExpand();
                }
              }}
            >
              {visualState === "tombstoned" ? (
                <Ban className="size-3.5 shrink-0 text-ink-600" aria-hidden />
              ) : null}
              {visualState === "overridden" ? (
                <Pencil className="size-3 shrink-0 text-ink-500" aria-hidden />
              ) : null}
              {visualState === "default" ? (
                <Sparkles className="size-3 shrink-0 text-evidence-600 opacity-80" aria-hidden />
              ) : null}
              <span className="min-w-0 truncate">{label}</span>
              {statusBadge(
                visualState,
                overrideEvidenceHref
                  ? { href: overrideEvidenceHref, onNavigate: onOverrideEvidenceNavigate }
                  : undefined,
              )}
              {trustRecoveryVisible ? (
                <span
                  className="ml-0.5 inline-flex shrink-0 items-center rounded border border-evidence-700/25 bg-evidence-100/90 px-1 py-0 text-[0.65rem] font-sans font-normal uppercase tracking-wide text-evidence-800"
                  data-trust-earn-back="true"
                >
                  Recovered
                </span>
              ) : null}
            </button>
          </HoverCardTrigger>
        </ContextMenuTrigger>

        <HoverCardContent className="text-left" side="top" align="start">
          <p className="text-xs font-sans font-semibold text-foreground">Citation preview</p>
          <dl className="mt-2 space-y-1 font-sans text-xs text-muted-foreground">
            <div className="flex justify-between gap-2">
              <dt className="shrink-0">ID</dt>
              <dd className="min-w-0 break-all text-ink-800">{preview.citationId}</dd>
            </div>
            <div className="flex justify-between gap-2">
              <dt className="shrink-0">Phase</dt>
              <dd className="text-ink-800">{preview.retrievalPhase}</dd>
            </div>
            <div className="flex justify-between gap-2">
              <dt className="shrink-0">Confidence</dt>
              <dd className="text-ink-800">{preview.confidence}</dd>
            </div>
            <div className="flex justify-between gap-2">
              <dt className="shrink-0">Timestamp</dt>
              <dd className="text-ink-800">{preview.signedTimestamp}</dd>
            </div>
          </dl>
        </HoverCardContent>

        <ContextMenuContent>
          <ContextMenuItem
            onSelect={() => {
              onViewEvidence();
            }}
          >
            <ScrollText className="size-4" aria-hidden />
            View evidence
          </ContextMenuItem>
          <ContextMenuItem
            onSelect={() => {
              onOverride();
            }}
            disabled={visualState === "tombstoned"}
          >
            <Pencil className="size-4" aria-hidden />
            Override
          </ContextMenuItem>
          <ContextMenuSeparator />
          <ContextMenuItem
            onSelect={() => {
              onCopyLink();
            }}
          >
            <Link2 className="size-4" aria-hidden />
            Copy link
          </ContextMenuItem>
          <ContextMenuItem
            onSelect={() => {
              onCiteInOverride();
            }}
            disabled={visualState === "tombstoned"}
          >
            <Quote className="size-4" aria-hidden />
            Cite in override
          </ContextMenuItem>
        </ContextMenuContent>
      </ContextMenu>
    </HoverCard>
  );
}
