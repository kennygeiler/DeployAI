"use client";

import * as React from "react";

import { Button } from "@/components/ui/button";

export type HorizontalTimelineEvent = {
  id: string;
  occurred_at: string;
  source_kind: string;
  summary: string;
  actor_kind?: string | null;
};

const HEIGHT = 140;
const AXIS_Y = 56;
const LANE_TOP = 72;
const LANE_STEP = 10;
const MAX_LANE = 6;
const MARGIN_X = 24;
const CIRCLE_R = 5;
const MIN_WIDTH = 600;
const PULSE_DURATION_MS = 2500;

const SOURCE_KIND_COLOR: Record<string, string> = {
  email_ingest: "#2563eb",
  meeting_webhook: "#16a34a",
  manual_capture: "#0891b2",
  llm_proposal_created: "#7c3aed",
  proposal_accepted: "#15803d",
  proposal_rejected: "#dc2626",
  matrix_node_created: "#0d9488",
  matrix_node_updated: "#0e7490",
  matrix_node_deleted: "#b91c1c",
  matrix_edge_created: "#0369a1",
  matrix_edge_deleted: "#9f1239",
  insight_opened: "#d97706",
  insight_closed: "#65a30d",
  recommendation_emitted: "#c026d3",
  recommendation_actioned: "#7e22ce",
  engagement_phase_change: "#0891b2",
  member_added: "#15803d",
  member_removed: "#9f1239",
  settings_change: "#525252",
  audit_other: "#737373",
  user_provisioned: "#0284c7",
  audit_decision: "#a16207",
  insight_snoozed: "#a16207",
  followup_task_created: "#1d4ed8",
  oracle_chat_turn: "#be185d",
};

const FALLBACK_COLOR = "#6b7280";

function colorFor(kind: string): string {
  return SOURCE_KIND_COLOR[kind] ?? FALLBACK_COLOR;
}

function dayKey(iso: string): string {
  return iso.slice(0, 10);
}

function formatRelative(iso: string, now: number): string {
  const t = Date.parse(iso);
  if (Number.isNaN(t)) return iso;
  const diffMs = now - t;
  const abs = Math.abs(diffMs);
  const dayMs = 86_400_000;
  const sign = diffMs >= 0 ? "ago" : "from now";
  if (abs < 60_000) return `just now`;
  if (abs < 3_600_000) {
    const m = Math.round(abs / 60_000);
    return `${m}m ${sign}`;
  }
  if (abs < dayMs) {
    const h = Math.round(abs / 3_600_000);
    return `${h}h ${sign}`;
  }
  if (abs < 30 * dayMs) {
    const d = Math.round(abs / dayMs);
    return `${d}d ${sign}`;
  }
  if (abs < 365 * dayMs) {
    const mo = Math.round(abs / (30 * dayMs));
    return `${mo}mo ${sign}`;
  }
  const y = Math.round(abs / (365 * dayMs));
  return `${y}y ${sign}`;
}

function truncate(text: string, max: number): string {
  if (text.length <= max) return text;
  return text.slice(0, max - 1).trimEnd() + "…";
}

type AxisTick = { x: number; label: string; major: boolean };

function buildAxisTicks(minTs: number, maxTs: number, width: number): AxisTick[] {
  if (!Number.isFinite(minTs) || !Number.isFinite(maxTs) || maxTs <= minTs) return [];
  const span = maxTs - minTs;
  const dayMs = 86_400_000;
  const spanDays = span / dayMs;

  const ticks: AxisTick[] = [];
  const start = new Date(minTs);
  const end = new Date(maxTs);

  const fmtMonth = (d: Date) => d.toLocaleString("en-US", { month: "short", timeZone: "UTC" });

  if (spanDays > 365) {
    let y = start.getUTCFullYear();
    while (y <= end.getUTCFullYear()) {
      for (let q = 0; q < 4; q++) {
        const tickDate = Date.UTC(y, q * 3, 1);
        if (tickDate < minTs || tickDate > maxTs) continue;
        const x = ((tickDate - minTs) / span) * width;
        ticks.push({
          x,
          label: q === 0 ? `Q1 ${y}` : `Q${q + 1}`,
          major: q === 0,
        });
      }
      y += 1;
    }
  } else {
    let y = start.getUTCFullYear();
    let m = start.getUTCMonth();
    while (true) {
      const tickDate = Date.UTC(y, m, 1);
      if (tickDate > maxTs) break;
      if (tickDate >= minTs) {
        const x = ((tickDate - minTs) / span) * width;
        const tmp = new Date(tickDate);
        ticks.push({
          x,
          label: m === 0 ? `${fmtMonth(tmp)} ${y}` : fmtMonth(tmp),
          major: m === 0,
        });
      }
      m += 1;
      if (m > 11) {
        m = 0;
        y += 1;
      }
    }
  }
  return ticks;
}

export function HorizontalTimeline({
  events,
  onSelect,
  focusedEventId,
}: {
  events: HorizontalTimelineEvent[];
  onSelect?: (eventId: string) => void;
  focusedEventId?: string | null;
}) {
  const wrapRef = React.useRef<HTMLDivElement | null>(null);
  const scrollRef = React.useRef<HTMLDivElement | null>(null);
  const [width, setWidth] = React.useState(MIN_WIDTH);
  const [hoverId, setHoverId] = React.useState<string | null>(null);
  const [hoverNow, setHoverNow] = React.useState<number>(0);
  const [pulseId, setPulseId] = React.useState<string | null>(null);
  const [zoom, setZoom] = React.useState(1);
  const circleRefs = React.useRef<Map<string, SVGCircleElement>>(new Map());

  const ZOOM_MIN = 0.5;
  const ZOOM_MAX = 4;
  const ZOOM_STEP = 1.25;
  const zoomIn = React.useCallback(
    () => setZoom((z) => Math.min(ZOOM_MAX, +(z * ZOOM_STEP).toFixed(3))),
    [],
  );
  const zoomOut = React.useCallback(
    () => setZoom((z) => Math.max(ZOOM_MIN, +(z / ZOOM_STEP).toFixed(3))),
    [],
  );
  const zoomReset = React.useCallback(() => setZoom(1), []);

  React.useEffect(() => {
    const measure = () => {
      const el = scrollRef.current ?? wrapRef.current;
      if (!el) return;
      const w = el.clientWidth;
      setWidth(Math.max(MIN_WIDTH, w || MIN_WIDTH));
    };
    measure();
    if (typeof ResizeObserver === "undefined") {
      window.addEventListener("resize", measure);
      return () => window.removeEventListener("resize", measure);
    }
    const ro = new ResizeObserver(() => measure());
    const target = scrollRef.current ?? wrapRef.current;
    if (target) ro.observe(target);
    return () => ro.disconnect();
  }, []);

  const baseInner = Math.max(MIN_WIDTH - MARGIN_X * 2, width - MARGIN_X * 2);
  const innerWidth = Math.round(baseInner * zoom);

  const range = React.useMemo(() => {
    if (events.length === 0) return null;
    let min = Infinity;
    let max = -Infinity;
    for (const ev of events) {
      const t = Date.parse(ev.occurred_at);
      if (Number.isNaN(t)) continue;
      if (t < min) min = t;
      if (t > max) max = t;
    }
    if (!Number.isFinite(min) || !Number.isFinite(max)) return null;
    if (min === max) {
      const pad = 86_400_000;
      return { min: min - pad, max: max + pad };
    }
    const pad = Math.max((max - min) * 0.05, 86_400_000);
    return { min: min - pad, max: max + pad };
  }, [events]);

  type Placed = {
    ev: HorizontalTimelineEvent;
    x: number;
    y: number;
    lane: number;
    color: string;
  };

  type DayBucket = {
    items: Placed[];
    overflow: number;
    x: number;
  };

  const { placed, buckets } = React.useMemo<{
    placed: Placed[];
    buckets: DayBucket[];
  }>(() => {
    if (!range || events.length === 0) return { placed: [], buckets: [] };
    const span = range.max - range.min;
    const grouped = new Map<string, HorizontalTimelineEvent[]>();
    for (const ev of events) {
      const k = dayKey(ev.occurred_at);
      let arr = grouped.get(k);
      if (!arr) {
        arr = [];
        grouped.set(k, arr);
      }
      arr.push(ev);
    }
    const out: Placed[] = [];
    const bucketsOut: DayBucket[] = [];
    for (const [, list] of grouped) {
      list.sort((a, b) => (a.occurred_at < b.occurred_at ? -1 : 1));
      const first = list[0];
      if (!first) continue;
      const t = Date.parse(first.occurred_at);
      const x = MARGIN_X + ((t - range.min) / span) * innerWidth;
      const placedHere: Placed[] = [];
      const take = Math.min(list.length, MAX_LANE);
      for (let i = 0; i < take; i++) {
        const ev = list[i];
        if (!ev) continue;
        placedHere.push({
          ev,
          x,
          y: LANE_TOP + i * LANE_STEP,
          lane: i,
          color: colorFor(ev.source_kind),
        });
      }
      out.push(...placedHere);
      bucketsOut.push({
        items: placedHere,
        overflow: Math.max(0, list.length - MAX_LANE),
        x,
      });
    }
    return { placed: out, buckets: bucketsOut };
  }, [events, range, innerWidth]);

  const ticks = React.useMemo(() => {
    if (!range) return [];
    return buildAxisTicks(range.min, range.max, innerWidth).map((t) => ({
      ...t,
      x: t.x + MARGIN_X,
    }));
  }, [range, innerWidth]);

  React.useEffect(() => {
    if (!focusedEventId) return;
    if (!placed.some((p) => p.ev.id === focusedEventId)) return;
    const setTid = window.setTimeout(() => setPulseId(focusedEventId), 0);
    const node = circleRefs.current.get(focusedEventId);
    const scrollEl = scrollRef.current;
    if (node && scrollEl) {
      const cx = Number(node.getAttribute("cx") || 0);
      const target = cx - scrollEl.clientWidth / 2;
      if (Number.isFinite(target) && typeof scrollEl.scrollTo === "function") {
        scrollEl.scrollTo({ left: Math.max(0, target), behavior: "smooth" });
      }
    }
    const tid = window.setTimeout(() => {
      setPulseId((cur) => (cur === focusedEventId ? null : cur));
    }, PULSE_DURATION_MS);
    return () => {
      clearTimeout(setTid);
      clearTimeout(tid);
    };
  }, [focusedEventId, placed]);

  const setCircleRef = React.useCallback((id: string, el: SVGCircleElement | null) => {
    if (el) circleRefs.current.set(id, el);
    else circleRefs.current.delete(id);
  }, []);

  const handleActivate = React.useCallback(
    (id: string) => {
      if (onSelect) onSelect(id);
    },
    [onSelect],
  );

  const hovered = hoverId ? (placed.find((p) => p.ev.id === hoverId) ?? null) : null;

  if (events.length === 0) {
    return (
      <div
        ref={wrapRef}
        data-testid="horizontal-timeline-empty"
        className="border-border flex h-[140px] items-center justify-center rounded-lg border text-sm text-ink-600"
      >
        No events in this range
      </div>
    );
  }

  const hoveredColor = hovered ? hovered.color : null;
  const hoveredEv = hovered?.ev ?? null;
  return (
    <div ref={wrapRef} data-testid="horizontal-timeline" className="space-y-2">
      <div className="flex items-start justify-between gap-3">
        <div
          aria-live="polite"
          data-testid="horizontal-timeline-info-card"
          className="border-border bg-paper-200 text-ink-800 flex min-h-[64px] flex-1 items-start gap-3 rounded-md border px-3 py-2 text-sm"
        >
          {hoveredEv ? (
            <>
              <span
                aria-hidden="true"
                className="mt-1 inline-block h-3 w-3 shrink-0 rounded-full"
                style={{ backgroundColor: hoveredColor ?? FALLBACK_COLOR }}
              />
              <div className="min-w-0 flex-1">
                <div className="text-ink-900 font-medium break-words">{hoveredEv.summary}</div>
                <div className="text-ink-600 mt-0.5 flex flex-wrap items-center gap-x-2 text-[11px]">
                  <span className="bg-ink-100 text-ink-800 rounded px-1.5 py-0.5 font-mono text-[10px] uppercase">
                    {hoveredEv.source_kind}
                  </span>
                  {hoveredEv.actor_kind ? <span>· {hoveredEv.actor_kind}</span> : null}
                  <span>
                    ·{" "}
                    {formatRelative(
                      hoveredEv.occurred_at,
                      hoverNow || Date.parse(hoveredEv.occurred_at),
                    )}
                  </span>
                  <span className="text-ink-500 font-mono text-[10px]">
                    · {hoveredEv.occurred_at}
                  </span>
                </div>
              </div>
            </>
          ) : (
            <p className="text-ink-500 text-xs">
              Hover or focus an event below for details. Use +/− to zoom the time axis.
            </p>
          )}
        </div>
        <div
          role="group"
          aria-label="Timeline zoom controls"
          className="flex shrink-0 items-center gap-1"
        >
          <Button
            type="button"
            variant="outline"
            size="sm"
            aria-label="Zoom out"
            data-testid="horizontal-timeline-zoom-out"
            onClick={zoomOut}
            disabled={zoom <= ZOOM_MIN + 0.001}
            className="h-7 w-7 px-0"
          >
            −
          </Button>
          <Button
            type="button"
            variant="outline"
            size="sm"
            aria-label="Reset zoom"
            data-testid="horizontal-timeline-zoom-reset"
            onClick={zoomReset}
            disabled={Math.abs(zoom - 1) < 0.001}
            className="h-7 px-2 text-xs"
          >
            {Math.round(zoom * 100)}%
          </Button>
          <Button
            type="button"
            variant="outline"
            size="sm"
            aria-label="Zoom in"
            data-testid="horizontal-timeline-zoom-in"
            onClick={zoomIn}
            disabled={zoom >= ZOOM_MAX - 0.001}
            className="h-7 w-7 px-0"
          >
            +
          </Button>
        </div>
      </div>
      <div
        ref={scrollRef}
        className="border-border bg-paper-50 relative overflow-x-auto rounded-lg border"
      >
        <svg
          role="img"
          aria-label={`Engagement timeline horizontal view (zoom ${Math.round(zoom * 100)}%)`}
          width={Math.max(width, innerWidth + MARGIN_X * 2)}
          height={HEIGHT}
          className="block"
        >
          <line
            x1={MARGIN_X}
            y1={AXIS_Y}
            x2={MARGIN_X + innerWidth}
            y2={AXIS_Y}
            stroke="#9ca3af"
            strokeWidth={1}
          />
          {ticks.map((t, i) => (
            <g key={`tick-${i}`} transform={`translate(${t.x}, 0)`}>
              <line
                x1={0}
                y1={AXIS_Y - (t.major ? 6 : 4)}
                x2={0}
                y2={AXIS_Y + (t.major ? 6 : 4)}
                stroke={t.major ? "#374151" : "#9ca3af"}
                strokeWidth={1}
              />
              <text
                x={0}
                y={AXIS_Y - 10}
                textAnchor="middle"
                fontSize={10}
                fill={t.major ? "#111827" : "#4b5563"}
                fontFamily="ui-sans-serif, system-ui, sans-serif"
              >
                {t.label}
              </text>
            </g>
          ))}

          {buckets.map((b, i) =>
            b.overflow > 0 ? (
              <text
                key={`overflow-${i}`}
                x={b.x}
                y={LANE_TOP + MAX_LANE * LANE_STEP + 10}
                textAnchor="middle"
                fontSize={9}
                fill="#4b5563"
                fontFamily="ui-sans-serif, system-ui, sans-serif"
                data-testid={`horizontal-timeline-overflow-${i}`}
              >
                +{b.overflow}
              </text>
            ) : null,
          )}

          {placed.map((p) => {
            const isPulse = pulseId === p.ev.id;
            const isHover = hoverId === p.ev.id;
            const ariaLabel = `${p.ev.source_kind} at ${p.ev.occurred_at}: ${truncate(p.ev.summary, 60)}`;
            return (
              <g key={p.ev.id}>
                {isPulse ? (
                  <circle
                    cx={p.x}
                    cy={p.y}
                    r={CIRCLE_R + 6}
                    fill="none"
                    stroke={p.color}
                    strokeWidth={2}
                    opacity={0.6}
                    data-testid={`horizontal-timeline-pulse-${p.ev.id}`}
                  >
                    <animate
                      attributeName="r"
                      values={`${CIRCLE_R + 2};${CIRCLE_R + 10};${CIRCLE_R + 2}`}
                      dur="1.2s"
                      repeatCount="indefinite"
                    />
                    <animate
                      attributeName="opacity"
                      values="0.8;0.1;0.8"
                      dur="1.2s"
                      repeatCount="indefinite"
                    />
                  </circle>
                ) : null}
                <circle
                  ref={(el) => setCircleRef(p.ev.id, el)}
                  cx={p.x}
                  cy={p.y}
                  r={CIRCLE_R}
                  fill={p.color}
                  stroke={isHover ? "#111827" : "#ffffff"}
                  strokeWidth={isHover ? 2 : 1}
                  tabIndex={0}
                  role="button"
                  aria-label={ariaLabel}
                  data-testid={`horizontal-timeline-event-${p.ev.id}`}
                  onMouseEnter={() => {
                    setHoverId(p.ev.id);
                    setHoverNow(Date.now());
                  }}
                  onMouseLeave={() => setHoverId((cur) => (cur === p.ev.id ? null : cur))}
                  onFocus={() => {
                    setHoverId(p.ev.id);
                    setHoverNow(Date.now());
                  }}
                  onBlur={() => setHoverId((cur) => (cur === p.ev.id ? null : cur))}
                  onClick={() => handleActivate(p.ev.id)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" || e.key === " ") {
                      e.preventDefault();
                      handleActivate(p.ev.id);
                    }
                  }}
                  style={{ cursor: "pointer", outline: "none" }}
                />
              </g>
            );
          })}
        </svg>
      </div>
    </div>
  );
}
