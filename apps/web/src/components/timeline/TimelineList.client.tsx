"use client";

import {
  CableIcon,
  CalendarIcon,
  ClipboardListIcon,
  FileTextIcon,
  GitBranchIcon,
  LightbulbIcon,
  MailIcon,
  MessageCircleIcon,
  ShieldCheckIcon,
  SparklesIcon,
  UserPlusIcon,
} from "lucide-react";
import * as React from "react";

import { Button } from "@/components/ui/button";
import type { LedgerEvent } from "@/lib/internal/ledger-cp";
import {
  formatActorId,
  humanSourceKindLabel,
  sourceKindIconName,
  type SourceKindIconName,
} from "@/lib/labels";

const EVENT_ROW_HEIGHT = 88;
const HEADER_ROW_HEIGHT = 36;
const OVERSCAN = 8;

/** Above this many events, cluster by week instead of by day (U8). */
const WEEK_CLUSTER_THRESHOLD = 150;

type IconComponent = React.ComponentType<{ className?: string; "aria-hidden"?: boolean }>;

const ICON_BY_NAME: Record<SourceKindIconName, IconComponent> = {
  mail: MailIcon,
  calendar: CalendarIcon,
  clipboard: ClipboardListIcon,
  sparkles: SparklesIcon,
  graph: GitBranchIcon,
  lightbulb: LightbulbIcon,
  shield: ShieldCheckIcon,
  person: UserPlusIcon,
  chat: MessageCircleIcon,
  cable: CableIcon,
  document: FileTextIcon,
};

function formatOccurredAt(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) {
    return iso;
  }
  return d.toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    year: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

function dayKey(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toISOString().slice(0, 10);
}

function weekKey(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  // Monday of the event's week (UTC) keys the cluster.
  const day = d.getUTCDay();
  const monday = new Date(d);
  monday.setUTCDate(d.getUTCDate() - ((day + 6) % 7));
  return monday.toISOString().slice(0, 10);
}

function formatDayHeader(key: string): string {
  const d = new Date(`${key}T00:00:00Z`);
  if (Number.isNaN(d.getTime())) return key;
  return d.toLocaleDateString(undefined, {
    weekday: "short",
    month: "short",
    day: "numeric",
    year: "numeric",
    timeZone: "UTC",
  });
}

function formatWeekHeader(key: string): string {
  const d = new Date(`${key}T00:00:00Z`);
  if (Number.isNaN(d.getTime())) return key;
  const label = d.toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
    year: "numeric",
    timeZone: "UTC",
  });
  return `Week of ${label}`;
}

type Row =
  | { type: "header"; key: string; label: string; count: number }
  | { type: "event"; key: string; event: LedgerEvent };

/** Flatten events into header + event rows, clustered by day (week at XL). */
export function buildClusteredRows(events: LedgerEvent[]): Row[] {
  const byWeek = events.length > WEEK_CLUSTER_THRESHOLD;
  const keyFor = byWeek ? weekKey : dayKey;
  const labelFor = byWeek ? formatWeekHeader : formatDayHeader;
  const rows: Row[] = [];
  let currentKey: string | null = null;
  let headerIdx = -1;
  for (const ev of events) {
    const key = keyFor(ev.occurred_at);
    if (key !== currentKey) {
      currentKey = key;
      headerIdx = rows.length;
      rows.push({ type: "header", key: `h-${key}-${rows.length}`, label: labelFor(key), count: 0 });
    }
    (rows[headerIdx] as Extract<Row, { type: "header" }>).count += 1;
    rows.push({ type: "event", key: ev.id, event: ev });
  }
  return rows;
}

export function TimelineList({
  events,
  onSelect,
  selectedId,
}: {
  events: LedgerEvent[];
  onSelect: (event: LedgerEvent) => void;
  selectedId?: string | null;
}) {
  const containerRef = React.useRef<HTMLDivElement | null>(null);
  const [scrollTop, setScrollTop] = React.useState(0);
  const [viewportHeight, setViewportHeight] = React.useState(600);

  React.useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    setViewportHeight(el.clientHeight);
    const onScroll = () => setScrollTop(el.scrollTop);
    el.addEventListener("scroll", onScroll, { passive: true });
    return () => el.removeEventListener("scroll", onScroll);
  }, []);

  const rows = React.useMemo(() => buildClusteredRows(events), [events]);

  // Prefix-sum offsets keep the windowing exact with two row heights.
  const offsets = React.useMemo(() => {
    const out = new Array<number>(rows.length + 1);
    out[0] = 0;
    for (let i = 0; i < rows.length; i++) {
      out[i + 1] = out[i]! + (rows[i]!.type === "header" ? HEADER_ROW_HEIGHT : EVENT_ROW_HEIGHT);
    }
    return out;
  }, [rows]);
  const totalHeight = offsets[rows.length] ?? 0;

  const findIndex = React.useCallback(
    (y: number): number => {
      let lo = 0;
      let hi = rows.length - 1;
      while (lo < hi) {
        const mid = (lo + hi + 1) >> 1;
        if ((offsets[mid] ?? 0) <= y) lo = mid;
        else hi = mid - 1;
      }
      return lo;
    },
    [rows.length, offsets],
  );

  const startIdx = rows.length === 0 ? 0 : Math.max(0, findIndex(scrollTop) - OVERSCAN);
  const endIdx =
    rows.length === 0
      ? 0
      : Math.min(rows.length, findIndex(scrollTop + viewportHeight) + OVERSCAN + 1);
  const visible = rows.slice(startIdx, endIdx);
  const topPad = offsets[startIdx] ?? 0;
  const bottomPad = Math.max(0, totalHeight - (offsets[endIdx] ?? 0));

  return (
    <div
      ref={containerRef}
      data-testid="timeline-list"
      className="border-border bg-background h-[70vh] flex-1 overflow-y-auto rounded-lg border"
    >
      {rows.length === 0 ? (
        <p className="text-ink-600 p-4 text-sm">
          No events recorded yet. Timeline populates as the team paste-imports emails / meetings or
          as the LLM proposes matrix changes.
        </p>
      ) : (
        <ul aria-label="Timeline events" className="divide-border divide-y">
          {topPad > 0 ? <li aria-hidden style={{ height: topPad }} /> : null}
          {visible.map((row) => {
            if (row.type === "header") {
              return (
                <li
                  key={row.key}
                  style={{ height: HEADER_ROW_HEIGHT }}
                  className="bg-paper-100 flex items-center justify-between px-4"
                  data-testid="timeline-day-header"
                >
                  <span className="text-ink-700 text-xs font-semibold">{row.label}</span>
                  <span className="text-ink-500 text-xs">
                    {row.count} event{row.count === 1 ? "" : "s"}
                  </span>
                </li>
              );
            }
            const ev = row.event;
            const isSelected = selectedId === ev.id;
            const Icon = ICON_BY_NAME[sourceKindIconName(ev.source_kind)];
            return (
              <li key={row.key} style={{ height: EVENT_ROW_HEIGHT }}>
                <Button
                  variant="ghost"
                  onClick={() => onSelect(ev)}
                  data-testid={`timeline-row-${ev.id}`}
                  aria-pressed={isSelected}
                  className={
                    "flex h-full w-full flex-col items-start gap-1 rounded-none px-4 py-2 text-left whitespace-normal " +
                    (isSelected ? "bg-ink-100" : "")
                  }
                >
                  <div className="flex w-full items-center justify-between gap-3">
                    <span className="text-ink-700 text-xs">{formatOccurredAt(ev.occurred_at)}</span>
                    <span className="bg-ink-100 text-ink-800 inline-flex items-center gap-1.5 rounded px-1.5 py-0.5 text-[10px] font-medium">
                      <Icon className="size-3" aria-hidden />
                      {humanSourceKindLabel(ev.source_kind)}
                    </span>
                  </div>
                  <p className="text-ink-700 line-clamp-2 text-sm">{ev.summary}</p>
                  <div className="text-ink-500 flex w-full items-center gap-2 text-xs">
                    <span>{ev.actor_kind}</span>
                    {ev.actor_id ? (
                      <span className="font-mono">{formatActorId(ev.actor_id)}</span>
                    ) : null}
                    {ev.affects.length > 0 ? (
                      <span className="ml-auto">{ev.affects.length} affected</span>
                    ) : null}
                  </div>
                </Button>
              </li>
            );
          })}
          {bottomPad > 0 ? <li aria-hidden style={{ height: bottomPad }} /> : null}
        </ul>
      )}
    </div>
  );
}
