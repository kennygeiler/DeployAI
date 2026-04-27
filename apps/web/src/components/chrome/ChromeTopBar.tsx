"use client";

import * as React from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  FreshnessChip,
  type FreshnessSurface,
  PhaseIndicator,
  type DeploymentPhaseId,
} from "@deployai/shared-ui";
import { Command, Loader2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { useStrategistSurface } from "@/lib/epic8/strategist-surface-context";
import { cn } from "@/lib/utils";

export type ChromeTopBarProps = {
  lastSyncedAt: number | null;
  /** Must match a key in NFR5 presets (evening reuses `digest` bands). */
  freshnessSurface: FreshnessSurface;
  currentPhaseId?: DeploymentPhaseId;
  className?: string;
  onOpenCommandPalette: () => void;
};

export function ChromeTopBar({
  lastSyncedAt,
  freshnessSurface,
  currentPhaseId = "P5_pilot",
  className: classNameProp,
  onOpenCommandPalette,
}: ChromeTopBarProps) {
  const pathname = usePathname();
  const { ingestionInProgress } = useStrategistSurface();

  const evidenceBreadcrumb = React.useMemo(() => {
    if (!pathname?.startsWith("/evidence/")) {
      return null;
    }
    const rest = pathname.slice("/evidence/".length);
    const nodeId = rest.split("/")[0] ?? "";
    const label =
      nodeId.length === 0 ? "…" : nodeId.length > 28 ? `${nodeId.slice(0, 14)}…` : nodeId;
    return (
      <nav
        aria-label="Breadcrumb"
        className="text-muted-foreground mr-1 hidden min-w-0 max-w-[min(28rem,42vw)] items-center gap-1 truncate text-xs md:flex"
      >
        <Link href="/digest" className="shrink-0 hover:underline">
          Strategist
        </Link>
        <span className="shrink-0" aria-hidden>
          /
        </span>
        <span className="text-ink-700 shrink-0 font-medium text-foreground">Evidence</span>
        <span className="shrink-0" aria-hidden>
          /
        </span>
        <span
          className="text-ink-900 min-w-0 truncate font-mono text-[0.7rem]"
          title={nodeId || undefined}
        >
          {label}
        </span>
      </nav>
    );
  }, [pathname]);

  return (
    <header
      className={cn(
        "bg-background/95 border-border flex h-14 shrink-0 items-center gap-3 border-b px-3 backdrop-blur md:px-4",
        classNameProp,
      )}
    >
      {evidenceBreadcrumb}
      <div className="min-w-0 shrink-0">
        <PhaseIndicator currentPhaseId={currentPhaseId} variant="locked" />
      </div>
      <div className="ml-auto flex min-w-0 items-center gap-2">
        {ingestionInProgress ? (
          <div
            role="status"
            className="border-border text-ink-800 bg-paper-100 inline-flex max-w-[10rem] items-center gap-1.5 rounded-md border px-2 py-1 text-xs font-medium sm:max-w-none"
            data-ingestion-active="true"
            aria-label="Ingestion in progress for this tenant"
          >
            <Loader2 className="text-evidence-700 size-3.5 shrink-0 animate-spin" aria-hidden />
            <span className="truncate">Ingesting…</span>
          </div>
        ) : null}
        <FreshnessChip
          lastSyncedAt={lastSyncedAt}
          surface={freshnessSurface}
          id="strategist-freshness"
        />
        <Button
          type="button"
          variant="outline"
          size="sm"
          className="inline-flex min-h-8 shrink-0 gap-1.5 font-sans"
          onClick={onOpenCommandPalette}
          title="Open command palette (⌘K / Ctrl+K)"
          id="strategist-command-palette-open"
          data-testid="command-palette-trigger"
        >
          <Command className="size-3.5" aria-hidden />
          <span className="text-xs">Search</span>
          <kbd className="text-muted-foreground border-border rounded border px-1 font-mono text-[0.65rem]">
            ⌘K
          </kbd>
        </Button>
      </div>
    </header>
  );
}
