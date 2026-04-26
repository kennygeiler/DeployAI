"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import type { CitationPreview } from "@deployai/shared-ui";
import { BookOpen, ListChecks, PlusCircle, UserRound, Waypoints } from "lucide-react";

import {
  CommandDialog,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
  CommandSeparator,
  CommandShortcut,
} from "@/components/ui/command";
import { MORNING_DIGEST_TOP } from "@/lib/epic8/mock-digest";

const navigateItems = [
  { href: "/digest", label: "Morning digest", value: "nav digest morning", Icon: Waypoints },
  { href: "/phase-tracking", label: "Phase & task tracking", value: "nav phase tasks tracking", Icon: ListChecks },
  { href: "/evening", label: "Evening synthesis", value: "nav evening synthesis", Icon: BookOpen },
  { href: "/validation-queue", label: "Validation queue (Epic 9)", value: "nav validation", Icon: UserRound },
] as const;

const actionItems = [
  {
    href: "/phase-tracking",
    label: "Resolve or claim in Action Queue",
    value: "action resolve claim queue",
    Icon: ListChecks,
  },
  { href: "/overrides", label: "Start override (attach evidence)", value: "action override", Icon: PlusCircle },
] as const;

/** Read-only preview (same fields as CitationChip hover card) — avoids nested buttons in cmdk. */
function CitationPreviewLine({ p }: { p: CitationPreview }) {
  return (
    <div
      className="border-border bg-paper-100 text-evidence-800 inline-flex max-w-[min(12rem,32vw)] shrink-0 flex-col gap-0.5 rounded border px-2 py-1.5 text-left font-mono text-[0.7rem] leading-tight"
      data-citation-preview="command"
    >
      <span className="text-ink-800 truncate" title={p.citationId}>
        {p.citationId.slice(0, 8)}…
      </span>
      <span className="text-ink-600 truncate" title={p.retrievalPhase}>
        {p.retrievalPhase}
      </span>
      <span className="text-ink-500 truncate">{p.confidence}</span>
    </div>
  );
}

export type StrategistCommandPaletteProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
};

/**
 * Story 8.6 — universal palette: navigate, stub actions, search with CitationChip previews.
 */
export function StrategistCommandPalette({ open, onOpenChange }: StrategistCommandPaletteProps) {
  const router = useRouter();
  const run = React.useCallback(
    (href: string) => {
      onOpenChange(false);
      router.push(href);
    },
    [onOpenChange, router],
  );

  return (
    <CommandDialog
      open={open}
      onOpenChange={onOpenChange}
      title="Strategist command palette"
      description="Search surfaces, actions, or canonical memory. Esc to close."
    >
      <CommandInput placeholder="Type a command, surface, or citation…" data-testid="command-palette-input" />
      <CommandList>
        <CommandEmpty>No results — try &quot;digest&quot;, &quot;phase&quot;, or a citation id.</CommandEmpty>
        <CommandGroup heading="Navigate">
          {navigateItems.map((n) => (
            <CommandItem
              key={n.href}
              value={n.value}
              onSelect={() => {
                run(n.href);
              }}
            >
              <n.Icon className="size-4" aria-hidden />
              <span className="min-w-0 flex-1 truncate">{n.label}</span>
            </CommandItem>
          ))}
        </CommandGroup>
        <CommandSeparator />
        <CommandGroup heading="Actions">
          {actionItems.map((a) => (
            <CommandItem
              key={a.label}
              value={a.value}
              onSelect={() => {
                run(a.href);
              }}
            >
              <a.Icon className="size-4" aria-hidden />
              {a.label}
            </CommandItem>
          ))}
        </CommandGroup>
        <CommandSeparator />
        <CommandGroup heading="Search (canonical memory preview)">
          {MORNING_DIGEST_TOP.map((row) => (
            <CommandItem
              key={row.id}
              value={`search ${row.label} ${row.preview.citationId} ${row.preview.retrievalPhase} ${row.preview.confidence}`}
              onSelect={() => {
                run(`/evidence/${row.id}`);
              }}
            >
              <div className="flex min-w-0 flex-1 items-start gap-2">
                <div className="min-w-0 flex-1">
                  <p className="text-foreground line-clamp-1 text-sm font-medium">{row.label}</p>
                  <p className="text-muted-foreground text-xs">Open evidence node in memory</p>
                </div>
                <CitationPreviewLine p={row.preview} />
              </div>
              <CommandShortcut>↵</CommandShortcut>
            </CommandItem>
          ))}
        </CommandGroup>
      </CommandList>
    </CommandDialog>
  );
}
