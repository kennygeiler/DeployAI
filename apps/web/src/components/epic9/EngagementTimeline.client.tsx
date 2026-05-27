"use client";

import { XIcon } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import * as React from "react";
import { toast } from "sonner";

import { TimestampLabel } from "@/components/common/TimestampLabel.client";
import {
  EngagementTimelineFilters,
  resolveAgentActivitySourceKinds,
  type AgentActivityChip,
} from "@/components/engagements/EngagementTimelineFilters";
import { McpTimelineRow } from "@/components/engagements/McpTimelineRow";
import { Button } from "@/components/ui/button";
import { HorizontalTimeline } from "@/components/epic9/HorizontalTimeline.client";
import { readStrategistBffErrorDescription } from "@/lib/bff/read-strategist-bff-error";
import type { LedgerEvent } from "@/lib/internal/ledger-cp";
import {
  isMcpConfigKind,
  isMcpKillswitchKind,
  isMcpOutboundCallKind,
} from "@/lib/internal/ledger-cp";

type TimelineEvent = {
  id: string;
  occurred_at: string;
  event_type: string;
  source_ref: string | null;
  summary: string;
};

export type AffectsFilter = {
  nodeId: string;
  nodeTitle: string;
  clearHref: string;
};

type WeekGroup = {
  key: string;
  label: string;
  events: TimelineEvent[];
};

type SourceState =
  | { kind: "ledger"; events: LedgerEvent[] }
  | { kind: "timeline"; events: TimelineEvent[] };

const DAY_MS = 24 * 60 * 60 * 1000;
const HIGHLIGHT_DURATION_MS = 2500;

function isoWeekKey(d: Date): { key: string; year: number; week: number } {
  const t = new Date(Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), d.getUTCDate()));
  const dayNum = t.getUTCDay() === 0 ? 7 : t.getUTCDay();
  t.setUTCDate(t.getUTCDate() + 4 - dayNum);
  const yearStart = new Date(Date.UTC(t.getUTCFullYear(), 0, 1));
  const week = Math.ceil(((t.getTime() - yearStart.getTime()) / DAY_MS + 1) / 7);
  const year = t.getUTCFullYear();
  return { key: `${year}-W${String(week).padStart(2, "0")}`, year, week };
}

function weekRangeLabel(year: number, week: number): string {
  const jan4 = new Date(Date.UTC(year, 0, 4));
  const jan4Day = jan4.getUTCDay() === 0 ? 7 : jan4.getUTCDay();
  const week1Monday = new Date(jan4);
  week1Monday.setUTCDate(jan4.getUTCDate() - (jan4Day - 1));
  const monday = new Date(week1Monday);
  monday.setUTCDate(week1Monday.getUTCDate() + (week - 1) * 7);
  const sunday = new Date(monday);
  sunday.setUTCDate(monday.getUTCDate() + 6);
  const fmt = (x: Date) =>
    `${x.toLocaleString("en-US", { month: "short", timeZone: "UTC" })} ${x.getUTCDate()}`;
  return `${fmt(monday)} – ${fmt(sunday)}, ${year}`;
}

function groupByWeek(events: TimelineEvent[]): WeekGroup[] {
  const buckets = new Map<string, WeekGroup>();
  for (const ev of events) {
    const d = new Date(ev.occurred_at);
    const { key, year, week } = isoWeekKey(d);
    let group = buckets.get(key);
    if (!group) {
      group = { key, label: `Week of ${weekRangeLabel(year, week)}`, events: [] };
      buckets.set(key, group);
    }
    group.events.push(ev);
  }
  const groups = Array.from(buckets.values());
  groups.sort((a, b) => (a.key < b.key ? 1 : a.key > b.key ? -1 : 0));
  for (const g of groups) {
    g.events.sort((a, b) => (a.occurred_at < b.occurred_at ? 1 : -1));
  }
  return groups;
}

function ledgerToTimelineEvent(ev: LedgerEvent): TimelineEvent {
  return {
    id: ev.id,
    occurred_at: ev.occurred_at,
    event_type: ev.source_kind,
    source_ref: ev.source_ref,
    summary: ev.summary,
  };
}

type ViewMode = "list" | "horizontal";

export function EngagementTimeline({
  engagementId,
  affectsFilter,
  eventId,
  initialSourceKinds = [],
  initialView,
}: {
  engagementId: string;
  affectsFilter?: AffectsFilter | null;
  eventId?: string | null;
  initialSourceKinds?: string[];
  initialView?: ViewMode;
}) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const urlView: ViewMode | null = searchParams?.get("view") === "horizontal" ? "horizontal" : null;
  const [view, setView] = React.useState<ViewMode>(urlView ?? initialView ?? "list");
  React.useEffect(() => {
    if (!urlView || urlView === view) return;
    const t = window.setTimeout(() => setView(urlView), 0);
    return () => clearTimeout(t);
  }, [urlView, view]);

  const [source, setSource] = React.useState<SourceState>({ kind: "timeline", events: [] });
  const [loading, setLoading] = React.useState(true);
  const [err, setErr] = React.useState<string | null>(null);
  const [sourceKinds, setSourceKinds] = React.useState<string[]>(initialSourceKinds);
  const [agentChip, setAgentChip] = React.useState<AgentActivityChip | null>(null);
  const [highlightedId, setHighlightedId] = React.useState<string | null>(null);
  const itemRefs = React.useRef<Map<string, HTMLLIElement>>(new Map());
  const jumpHandledRef = React.useRef<string | null>(null);
  const broadenedForRef = React.useRef<string | null>(null);

  const affectsNodeId = affectsFilter?.nodeId ?? null;

  React.useEffect(() => {
    let cancelled = false;
    void (async () => {
      setLoading(true);
      try {
        // Always fetch from /ledger so list + horizontal share one source. The
        // legacy /timeline route returned a thinner shape that produced "no
        // interactions" empty-state on rich BlueState data even though /ledger
        // had hundreds of rows. /ledger is the authoritative event source.
        const qs = new URLSearchParams({ limit: "500" });
        if (affectsNodeId) {
          qs.set("affects_entity_kind", "matrix_node");
          qs.set("affects_entity_id", affectsNodeId);
        }
        const r = await fetch(
          `/api/bff/engagements/${encodeURIComponent(engagementId)}/ledger?${qs.toString()}`,
          { cache: "no-store" },
        );
        if (cancelled) return;
        if (!r.ok) {
          setErr(await readStrategistBffErrorDescription(r));
          setSource({ kind: "ledger", events: [] });
          return;
        }
        const body = (await r.json()) as { events?: LedgerEvent[] };
        const ledger = Array.isArray(body.events) ? body.events : [];
        setErr(null);
        setSource({ kind: "ledger", events: ledger });
      } catch (e) {
        if (!cancelled) {
          setErr(e instanceof Error ? e.message : "Could not load timeline.");
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [engagementId, affectsNodeId, eventId]);

  // Compose the active filter: explicit per-source-kind chips combine
  // with the agent-activity chip group (Wave 3I). When the agent chip is
  // active we union its source_kinds with whatever the strategist already
  // picked, so toggling "External (MCP)" never *hides* an unrelated kind
  // the user was already inspecting.
  const activeSourceKinds = React.useMemo<readonly string[]>(() => {
    const chipKinds = resolveAgentActivitySourceKinds(agentChip, {
      includeMcpAuxiliary: true,
    });
    if (chipKinds.length === 0) return sourceKinds;
    if (sourceKinds.length === 0) return chipKinds;
    return Array.from(new Set([...sourceKinds, ...chipKinds]));
  }, [sourceKinds, agentChip]);

  // id → full LedgerEvent lookup so the custom MCP row renderer can read
  // the redacted detail blob (connector_kind, tool, latency_ms) that the
  // thinner TimelineEvent shape strips out.
  const ledgerById = React.useMemo<Map<string, LedgerEvent>>(() => {
    if (source.kind !== "ledger") return new Map();
    return new Map(source.events.map((ev) => [ev.id, ev]));
  }, [source]);

  const events = React.useMemo<TimelineEvent[]>(() => {
    if (source.kind === "timeline") return source.events;
    const allow = activeSourceKinds.length === 0 ? null : new Set(activeSourceKinds);
    return source.events
      .filter((ev) => (allow ? allow.has(ev.source_kind) : true))
      .map(ledgerToTimelineEvent);
  }, [source, activeSourceKinds]);

  const horizontalEvents = React.useMemo(() => {
    if (source.kind === "ledger") {
      const allow = activeSourceKinds.length === 0 ? null : new Set(activeSourceKinds);
      return source.events
        .filter((ev) => (allow ? allow.has(ev.source_kind) : true))
        .map((ev) => ({
          id: ev.id,
          occurred_at: ev.occurred_at,
          source_kind: ev.source_kind,
          summary: ev.summary,
          actor_kind: ev.actor_kind,
        }));
    }
    return events.map((ev) => ({
      id: ev.id,
      occurred_at: ev.occurred_at,
      source_kind: ev.event_type,
      summary: ev.summary,
      actor_kind: null,
    }));
  }, [source, activeSourceKinds, events]);

  // Event-jump: scroll & highlight once events have rendered. Broaden the
  // source-kind filter automatically if the target is filtered out, otherwise
  // toast "Event not on this page" when the id isn't in the loaded set.
  React.useEffect(() => {
    if (!eventId || loading) return;
    if (jumpHandledRef.current === eventId) return;
    const ledgerEvents = source.kind === "ledger" ? source.events : [];
    const inLedger = ledgerEvents.some((ev) => ev.id === eventId);
    const visible = events.some((ev) => ev.id === eventId);

    if (visible) {
      jumpHandledRef.current = eventId;
      const el = itemRefs.current.get(eventId);
      if (el) {
        el.scrollIntoView({ behavior: "smooth", block: "center" });
      }
      const onTimer = window.setTimeout(() => {
        setHighlightedId((cur) => (cur === eventId ? null : cur));
      }, HIGHLIGHT_DURATION_MS);
      const setNow = window.setTimeout(() => setHighlightedId(eventId), 0);
      return () => {
        clearTimeout(onTimer);
        clearTimeout(setNow);
      };
    }

    if (source.kind === "ledger" && inLedger && (sourceKinds.length > 0 || agentChip !== null)) {
      if (broadenedForRef.current !== eventId) {
        broadenedForRef.current = eventId;
        const t = window.setTimeout(() => {
          setSourceKinds([]);
          setAgentChip(null);
          toast("Cleared filters to show this event");
        }, 0);
        return () => clearTimeout(t);
      }
      return;
    }

    if (source.kind === "ledger" && source.events.length > 0 && !inLedger) {
      jumpHandledRef.current = eventId;
      toast("Event not on this page");
      return;
    }
    if (source.kind === "timeline" && source.events.length > 0 && !visible) {
      jumpHandledRef.current = eventId;
      toast("Event not on this page");
      return;
    }
  }, [eventId, loading, source, events, sourceKinds, agentChip]);

  const groups = React.useMemo(() => groupByWeek(events), [events]);

  const clearSourceKind = React.useCallback((kind: string) => {
    setSourceKinds((cur) => cur.filter((k) => k !== kind));
  }, []);

  const setItemRef = React.useCallback((id: string, el: HTMLLIElement | null) => {
    if (el) {
      itemRefs.current.set(id, el);
    } else {
      itemRefs.current.delete(id);
    }
  }, []);

  const buildViewHref = React.useCallback(
    (target: ViewMode): string => {
      const sp = new URLSearchParams(searchParams?.toString() ?? "");
      if (target === "horizontal") sp.set("view", "horizontal");
      else sp.delete("view");
      const qs = sp.toString();
      return qs ? `${pathname}?${qs}` : (pathname ?? "");
    },
    [pathname, searchParams],
  );

  const handleSetView = React.useCallback(
    (target: ViewMode) => {
      setView(target);
      const href = buildViewHref(target);
      if (router && href) router.replace(href, { scroll: false });
    },
    [buildViewHref, router],
  );

  const handleHorizontalSelect = React.useCallback(
    (selectedId: string) => {
      const sp = new URLSearchParams(searchParams?.toString() ?? "");
      sp.set("event", selectedId);
      sp.set("view", "horizontal");
      const qs = sp.toString();
      const href = qs ? `${pathname}?${qs}` : (pathname ?? "");
      if (router && href) router.replace(href, { scroll: false });
    },
    [pathname, router, searchParams],
  );

  return (
    <section aria-labelledby="engagement-timeline-heading" className="space-y-3">
      <div className="flex items-center justify-between gap-3">
        <h2 id="engagement-timeline-heading" className="text-ink-800 text-sm font-semibold">
          Timeline
        </h2>
        <div
          role="group"
          aria-label="Timeline view mode"
          className="inline-flex gap-1"
          data-testid="timeline-view-toggle"
        >
          <Button
            type="button"
            variant={view === "list" ? "default" : "outline"}
            size="xs"
            aria-pressed={view === "list"}
            data-testid="timeline-view-toggle-list"
            onClick={() => handleSetView("list")}
          >
            List
          </Button>
          <Button
            type="button"
            variant={view === "horizontal" ? "default" : "outline"}
            size="xs"
            aria-pressed={view === "horizontal"}
            data-testid="timeline-view-toggle-horizontal"
            onClick={() => handleSetView("horizontal")}
          >
            Horizontal
          </Button>
        </div>
      </div>
      <EngagementTimelineFilters selected={agentChip} onChange={setAgentChip} />
      {affectsFilter || sourceKinds.length > 0 ? (
        <div
          role="group"
          aria-label="Active timeline filters"
          className="flex flex-wrap items-center gap-2"
          data-testid="timeline-filter-rail"
        >
          {affectsFilter ? (
            <span
              data-testid="affects-chip"
              className="border-border bg-paper-50 text-ink-800 inline-flex items-center gap-1 rounded-full border px-2 py-1 text-xs"
            >
              <span className="text-ink-500">Showing events affecting</span>
              <span className="font-medium">{affectsFilter.nodeTitle}</span>
              <Link
                href={affectsFilter.clearHref}
                aria-label="Clear node filter"
                data-testid="affects-chip-clear"
                className="text-ink-600 hover:text-ink-900 ml-1 inline-flex items-center justify-center rounded-full"
              >
                <XIcon className="size-3" aria-hidden />
              </Link>
            </span>
          ) : null}
          {sourceKinds.map((k) => (
            <span
              key={k}
              data-testid={`source-kind-chip-${k}`}
              className="border-border bg-paper-50 text-ink-800 inline-flex items-center gap-1 rounded-full border px-2 py-1 text-xs"
            >
              <span className="text-ink-500">Source:</span>
              <span className="font-mono">{k}</span>
              <Button
                type="button"
                variant="ghost"
                size="icon"
                aria-label={`Clear ${k} source filter`}
                data-testid={`source-kind-chip-clear-${k}`}
                onClick={() => clearSourceKind(k)}
                className="text-ink-600 hover:text-ink-900 ml-1 size-4 rounded-full p-0"
              >
                <XIcon className="size-3" aria-hidden />
              </Button>
            </span>
          ))}
        </div>
      ) : null}
      {err ? <p className="text-error-700 text-sm">{err}</p> : null}
      {loading ? (
        <p className="text-ink-600 text-sm">Loading…</p>
      ) : err ? null : view === "horizontal" ? (
        <HorizontalTimeline
          events={horizontalEvents}
          focusedEventId={eventId ?? null}
          onSelect={handleHorizontalSelect}
        />
      ) : groups.length === 0 ? (
        <p className="text-ink-600 text-sm">
          {affectsFilter
            ? `No timeline events affect ${affectsFilter.nodeTitle}.`
            : "No interactions yet — paste one below or wait for ingestion."}
        </p>
      ) : (
        <div className="space-y-4">
          {groups.map((g) => (
            <div key={g.key} className="space-y-2">
              <h3 className="text-ink-700 text-xs font-semibold uppercase">{g.label}</h3>
              <ul className="border-border divide-border divide-y rounded-lg border text-sm">
                {g.events.map((ev) => {
                  const isHighlighted = highlightedId === ev.id;
                  const kind = ev.event_type;
                  const isMcp =
                    isMcpOutboundCallKind(kind) ||
                    isMcpConfigKind(kind) ||
                    isMcpKillswitchKind(kind);
                  const mcpEvent = isMcp ? ledgerById.get(ev.id) : undefined;
                  return (
                    <li
                      key={ev.id}
                      ref={(el) => setItemRef(ev.id, el)}
                      data-testid={`timeline-event-${ev.id}`}
                      aria-current={isHighlighted ? "true" : undefined}
                      className={
                        "space-y-1 px-3 py-2 transition-colors " +
                        (isHighlighted ? "bg-warning-100 ring-warning-400 ring-2" : "")
                      }
                    >
                      {isMcp && mcpEvent ? (
                        <McpTimelineRow event={mcpEvent} />
                      ) : (
                        <>
                          <div className="flex items-center justify-between gap-3">
                            <TimestampLabel value={ev.occurred_at} className="text-ink-700" />
                            <span className="bg-ink-100 text-ink-800 rounded px-1.5 py-0.5 font-mono text-[10px] uppercase">
                              {ev.event_type}
                            </span>
                          </div>
                          <p className="text-ink-700 whitespace-pre-line">{ev.summary}</p>
                          {ev.source_ref ? (
                            <p className="text-ink-500 font-mono text-xs">{ev.source_ref}</p>
                          ) : null}
                        </>
                      )}
                    </li>
                  );
                })}
              </ul>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}
