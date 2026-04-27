"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import type { CitationPreview } from "@deployai/shared-ui";
import { BookOpen, ListChecks, PlusCircle, UserRound, Video, Waypoints } from "lucide-react";

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
import { parseStrategistMemorySearchResponse } from "@/lib/bff/parse-strategist-memory-search";
import type { MemorySearchHit } from "@/lib/bff/memory-search-mock";
import { MORNING_DIGEST_TOP } from "@/lib/epic8/mock-digest";

const navigateItems = [
  { href: "/digest", label: "Morning digest", value: "nav digest morning", Icon: Waypoints },
  {
    href: "/in-meeting",
    label: "In-meeting alert (MVP mock)",
    value: "nav in meeting alert",
    Icon: Video,
  },
  {
    href: "/phase-tracking",
    label: "Phase & task tracking",
    value: "nav phase tasks tracking",
    Icon: ListChecks,
  },
  { href: "/evening", label: "Evening synthesis", value: "nav evening synthesis", Icon: BookOpen },
  {
    href: "/validation-queue",
    label: "Validation queue (Epic 9)",
    value: "nav validation",
    Icon: UserRound,
  },
] as const;

const actionItems = [
  {
    href: "/phase-tracking",
    label: "Resolve or claim in Action Queue",
    value: "action resolve claim queue",
    Icon: ListChecks,
  },
  {
    href: "/overrides",
    label: "Start override (attach evidence)",
    value: "action override",
    Icon: PlusCircle,
  },
] as const;

const DEBOUNCE_MS = 320;

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

function kindLabel(k: MemorySearchHit["kind"]): string {
  return k === "action_queue" ? "Action queue" : "Digest";
}

export type StrategistCommandPaletteProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
};

/**
 * Story 8.6 — Cmd+K: navigate, actions, and memory search via
 * `GET /api/bff/strategist-memory-search?q=…` (debounced).
 */
export function StrategistCommandPalette({ open, onOpenChange }: StrategistCommandPaletteProps) {
  const router = useRouter();
  const [search, setSearch] = React.useState("");
  const [debounced, setDebounced] = React.useState("");
  const [bffHits, setBffHits] = React.useState<MemorySearchHit[]>([]);
  const [source, setSource] = React.useState<string | null>(null);
  const [searchLoading, setSearchLoading] = React.useState(false);
  const [searchError, setSearchError] = React.useState<string | null>(null);
  const req = React.useRef(0);

  const onPaletteOpenChange = React.useCallback(
    (next: boolean) => {
      if (!next) {
        setSearch("");
        setDebounced("");
        setBffHits([]);
        setSource(null);
        setSearchError(null);
        setSearchLoading(false);
        req.current += 1;
      }
      onOpenChange(next);
    },
    [onOpenChange],
  );

  const run = React.useCallback(
    (href: string) => {
      onPaletteOpenChange(false);
      router.push(href);
    },
    [onPaletteOpenChange, router],
  );

  React.useEffect(() => {
    const t = setTimeout(() => {
      setDebounced(search);
    }, DEBOUNCE_MS);
    return () => clearTimeout(t);
  }, [search]);

  React.useEffect(() => {
    if (!open) {
      return;
    }
    const q = debounced.trim();
    if (q.length < 1) {
      req.current += 1;
      return;
    }
    const id = (req.current += 1);
    void (async () => {
      await Promise.resolve();
      if (id !== req.current) {
        return;
      }
      setSearchLoading(true);
      setSearchError(null);
      try {
        const u = new URL("/api/bff/strategist-memory-search", window.location.origin);
        u.searchParams.set("q", q);
        const r = await fetch(u.toString(), { cache: "no-store" });
        const j = (await r.json()) as unknown;
        if (id !== req.current) {
          return;
        }
        if (!r.ok) {
          setSearchError(
            typeof (j as { error?: string }).error === "string"
              ? (j as { error: string }).error
              : r.statusText,
          );
          setBffHits([]);
          setSource("error");
          return;
        }
        const p = parseStrategistMemorySearchResponse(j);
        if (id !== req.current) {
          return;
        }
        setBffHits(p.hits);
        setSource(p.source);
        setSearchError(null);
      } catch (e) {
        if (id !== req.current) {
          return;
        }
        setSearchError(e instanceof Error ? e.message : "Search failed");
        setBffHits([]);
        setSource("error");
      } finally {
        if (id === req.current) {
          setSearchLoading(false);
        }
      }
    })();
  }, [debounced, open]);

  const showBff = debounced.trim().length > 0;
  const displayLoading = showBff && searchLoading;
  const searchHeading = showBff
    ? "Search (canonical memory — BFF)"
    : "Search (recent — type to search memory)";

  return (
    <CommandDialog
      open={open}
      onOpenChange={onPaletteOpenChange}
      title="Strategist command palette"
      description="Navigate surfaces, run actions, and search. Results come from /api/bff/strategist-memory-search when you type. Esc to close."
      commandProps={{ label: "Strategist command" }}
    >
      <CommandInput
        placeholder="Type a command, surface, or memory query…"
        data-testid="command-palette-input"
        value={search}
        onValueChange={setSearch}
      />
      <CommandList>
        <CommandEmpty>
          {displayLoading
            ? "Loading…"
            : "No results — try “digest”, “phase”, or a keyword from an evidence item."}
        </CommandEmpty>
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
        <CommandGroup heading={searchHeading} data-memory-search={showBff ? "bff" : "recent"}>
          {showBff && searchError ? (
            <div className="text-destructive px-2 py-2 text-xs" data-memory-search-error>
              {searchError}
            </div>
          ) : null}
          {displayLoading ? (
            <div className="text-muted-foreground px-2 py-2 text-sm" data-memory-search-loading>
              Searching memory…
            </div>
          ) : null}
          {!showBff
            ? MORNING_DIGEST_TOP.map((row) => (
                <CommandItem
                  key={row.id}
                  value={`search-recent ${row.label} ${row.preview.citationId} ${row.preview.retrievalPhase} ${row.preview.confidence}`}
                  onSelect={() => {
                    run(`/evidence/${row.id}`);
                  }}
                >
                  <div className="flex min-w-0 flex-1 items-start gap-2">
                    <div className="min-w-0 flex-1">
                      <p className="text-foreground line-clamp-1 text-sm font-medium">
                        {row.label}
                      </p>
                      <p className="text-muted-foreground text-xs">
                        Open evidence (recent preview)
                      </p>
                    </div>
                    <CitationPreviewLine p={row.preview} />
                  </div>
                  <CommandShortcut>↵</CommandShortcut>
                </CommandItem>
              ))
            : bffHits.map((h) => {
                const row = MORNING_DIGEST_TOP.find((d) => d.id === h.id);
                return (
                  <CommandItem
                    key={`${h.kind}-${h.id}`}
                    data-testid="memory-search-hit"
                    value={`search-bff ${h.label} ${h.id} ${h.queryText} ${h.kind} ${source ?? ""}`}
                    onSelect={() => {
                      run(`/evidence/${h.id}`);
                    }}
                  >
                    <div className="flex min-w-0 flex-1 items-start gap-2">
                      <div className="min-w-0 flex-1">
                        <p className="text-foreground line-clamp-1 text-sm font-medium">
                          {h.label}
                        </p>
                        <p className="text-muted-foreground text-xs">
                          {kindLabel(h.kind)}
                          {source ? ` — ${source}` : ""}
                        </p>
                      </div>
                      {row ? <CitationPreviewLine p={row.preview} /> : null}
                    </div>
                    <CommandShortcut>↵</CommandShortcut>
                  </CommandItem>
                );
              })}
          {!displayLoading && showBff && bffHits.length === 0 && !searchError ? (
            <p className="text-muted-foreground px-2 py-2 text-sm">
              No memory matches for that query.
            </p>
          ) : null}
        </CommandGroup>
      </CommandList>
    </CommandDialog>
  );
}
