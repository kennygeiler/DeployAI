"use client";

import { XIcon } from "lucide-react";
import Link from "next/link";
import * as React from "react";

import { TimestampLabel } from "@/components/common/TimestampLabel.client";
import { readStrategistBffErrorDescription } from "@/lib/bff/read-strategist-bff-error";
import type { LedgerEvent } from "@/lib/internal/ledger-cp";

type TimelineEvent = {
  id: string;
  occurred_at: string;
  event_type: string;
  source_ref: string | null;
  summary: string;
};

export type StakeholderFilter = {
  id: string;
  title: string;
  email: string | null;
  evidenceEventIds: string[];
  clearHref: string;
};

type WeekGroup = {
  key: string;
  label: string;
  events: TimelineEvent[];
};

const DAY_MS = 24 * 60 * 60 * 1000;

function isoWeekKey(d: Date): { key: string; year: number; week: number } {
  // ISO 8601 week: Thursday in current week decides the year. Days from
  // Monday=1..Sunday=7. Standard algorithm — no library needed.
  const t = new Date(Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), d.getUTCDate()));
  const dayNum = t.getUTCDay() === 0 ? 7 : t.getUTCDay();
  t.setUTCDate(t.getUTCDate() + 4 - dayNum);
  const yearStart = new Date(Date.UTC(t.getUTCFullYear(), 0, 1));
  const week = Math.ceil(((t.getTime() - yearStart.getTime()) / DAY_MS + 1) / 7);
  const year = t.getUTCFullYear();
  return { key: `${year}-W${String(week).padStart(2, "0")}`, year, week };
}

function weekRangeLabel(year: number, week: number): string {
  // ISO week 1 is the week containing Jan 4 — compute the Monday of that week.
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
  // Newest week first; within a week, newest event first.
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

function ledgerMatchesStakeholder(ev: LedgerEvent, filter: StakeholderFilter): boolean {
  if (filter.evidenceEventIds.includes(ev.id)) return true;
  if (filter.email && ev.actor_id && ev.actor_id.toLowerCase() === filter.email.toLowerCase()) {
    return true;
  }
  return false;
}

export function EngagementTimeline({
  engagementId,
  stakeholderFilter,
}: {
  engagementId: string;
  stakeholderFilter?: StakeholderFilter;
}) {
  const [events, setEvents] = React.useState<TimelineEvent[]>([]);
  const [loading, setLoading] = React.useState(true);
  const [err, setErr] = React.useState<string | null>(null);
  const filterId = stakeholderFilter?.id ?? null;
  const filterEmail = stakeholderFilter?.email ?? null;
  const filterEvidenceKey = stakeholderFilter?.evidenceEventIds.join(",") ?? "";

  React.useEffect(() => {
    let cancelled = false;
    void (async () => {
      setLoading(true);
      try {
        // Stakeholder filter requires actor_id + per-event ids only the ledger
        // BFF exposes — fall back to the lighter /timeline route otherwise so
        // the engagement-detail page surface stays cheap.
        if (filterId) {
          const r = await fetch(
            `/api/bff/engagements/${encodeURIComponent(engagementId)}/ledger?limit=500`,
            { cache: "no-store" },
          );
          if (cancelled) return;
          if (!r.ok) {
            setErr(await readStrategistBffErrorDescription(r));
            setEvents([]);
            return;
          }
          const body = (await r.json()) as { events?: LedgerEvent[] };
          const ledger = Array.isArray(body.events) ? body.events : [];
          const filter: StakeholderFilter = {
            id: filterId,
            title: stakeholderFilter?.title ?? "",
            email: filterEmail,
            evidenceEventIds: filterEvidenceKey ? filterEvidenceKey.split(",") : [],
            clearHref: stakeholderFilter?.clearHref ?? "#",
          };
          const filtered = ledger
            .filter((ev) => ledgerMatchesStakeholder(ev, filter))
            .map(ledgerToTimelineEvent);
          setErr(null);
          setEvents(filtered);
          return;
        }
        const r = await fetch(`/api/bff/engagements/${encodeURIComponent(engagementId)}/timeline`, {
          cache: "no-store",
        });
        if (cancelled) {
          return;
        }
        if (!r.ok) {
          setErr(await readStrategistBffErrorDescription(r));
          return;
        }
        const body = (await r.json()) as { events?: TimelineEvent[] };
        setErr(null);
        setEvents(Array.isArray(body.events) ? body.events : []);
      } catch (e) {
        if (!cancelled) {
          setErr(e instanceof Error ? e.message : "Could not load timeline.");
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    })();
    return () => {
      cancelled = true;
    };
    // stakeholderFilter is captured by id/email/evidence — its onClear ref is
    // stable from the parent and not a fetch input.
  }, [engagementId, filterId, filterEmail, filterEvidenceKey, stakeholderFilter]);

  const groups = React.useMemo(() => groupByWeek(events), [events]);

  return (
    <section aria-labelledby="engagement-timeline-heading" className="space-y-3">
      <div className="flex items-center justify-between gap-3">
        <h2 id="engagement-timeline-heading" className="text-ink-800 text-sm font-semibold">
          Timeline
        </h2>
      </div>
      {stakeholderFilter ? (
        <div
          role="group"
          aria-label="Active timeline filters"
          className="flex flex-wrap items-center gap-2"
          data-testid="timeline-filter-rail"
        >
          <span
            data-testid="stakeholder-chip"
            className="border-border bg-paper-50 text-ink-800 inline-flex items-center gap-1 rounded-full border px-2 py-1 text-xs"
          >
            <span className="text-ink-500">Stakeholder:</span>
            <span className="font-medium">{stakeholderFilter.title}</span>
            <Link
              href={stakeholderFilter.clearHref}
              aria-label="Clear stakeholder filter"
              data-testid="stakeholder-chip-clear"
              className="text-ink-600 hover:text-ink-900 ml-1 inline-flex items-center justify-center rounded-full"
            >
              <XIcon className="size-3" aria-hidden />
            </Link>
          </span>
        </div>
      ) : null}
      {err ? <p className="text-error-700 text-sm">{err}</p> : null}
      {loading ? (
        <p className="text-ink-600 text-sm">Loading…</p>
      ) : err ? null : groups.length === 0 ? (
        <p className="text-ink-600 text-sm">
          {stakeholderFilter
            ? `No timeline events match ${stakeholderFilter.title}.`
            : "No interactions yet — paste one below or wait for ingestion."}
        </p>
      ) : (
        <div className="space-y-4">
          {groups.map((g) => (
            <div key={g.key} className="space-y-2">
              <h3 className="text-ink-700 text-xs font-semibold uppercase">{g.label}</h3>
              <ul className="border-border divide-border divide-y rounded-lg border text-sm">
                {g.events.map((ev) => (
                  <li key={ev.id} className="space-y-1 px-3 py-2">
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
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}
