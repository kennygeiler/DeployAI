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
import Link from "next/link";
import * as React from "react";

import { TimestampLabel } from "@/components/common/TimestampLabel.client";
import { readStrategistBffErrorDescription } from "@/lib/bff/read-strategist-bff-error";
import type { LedgerEvent } from "@/lib/internal/ledger-cp";
import {
  humanSourceKindLabel,
  sourceKindIconName,
  stripRedundantKindPrefix,
  type SourceKindIconName,
} from "@/lib/labels";

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

function iconFor(sourceKind: string): IconComponent {
  return ICON_BY_NAME[sourceKindIconName(sourceKind)];
}

export function RecentActivityStrip({ engagementId }: { engagementId: string }) {
  const [events, setEvents] = React.useState<LedgerEvent[]>([]);
  const [loading, setLoading] = React.useState(true);
  const [err, setErr] = React.useState<string | null>(null);

  React.useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const r = await fetch(
          `/api/bff/engagements/${encodeURIComponent(engagementId)}/ledger?limit=5`,
          { cache: "no-store" },
        );
        if (cancelled) return;
        if (!r.ok) {
          setErr(await readStrategistBffErrorDescription(r));
          setEvents([]);
          return;
        }
        const body = (await r.json()) as { events?: LedgerEvent[] };
        setErr(null);
        setEvents(Array.isArray(body.events) ? body.events.slice(0, 5) : []);
      } catch (e) {
        if (!cancelled) {
          setErr(e instanceof Error ? e.message : "Could not load recent activity.");
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [engagementId]);

  if (loading) {
    return (
      <section aria-label="recent activity" data-testid="recent-activity-strip">
        <p className="text-ink-600 text-sm">Loading recent activity…</p>
      </section>
    );
  }

  if (err) {
    return (
      <section aria-label="recent activity" data-testid="recent-activity-strip">
        <p role="alert" className="text-red-ink text-sm">
          {err}
        </p>
      </section>
    );
  }

  if (events.length === 0) {
    return (
      <section aria-label="recent activity" data-testid="recent-activity-strip">
        <p className="text-ink-600 text-sm" data-testid="recent-activity-empty">
          No recent activity.
        </p>
      </section>
    );
  }

  return (
    <section aria-label="recent activity" data-testid="recent-activity-strip">
      <ol
        className="flex snap-x snap-mandatory gap-2 overflow-x-auto pb-2"
        data-testid="recent-activity-list"
      >
        {events.map((ev) => {
          const Icon = iconFor(ev.source_kind);
          const href = `/engagements/${encodeURIComponent(engagementId)}/timeline?event=${encodeURIComponent(ev.id)}`;
          const kindLabel = humanSourceKindLabel(ev.source_kind);
          const summary = stripRedundantKindPrefix(ev.summary, ev.source_kind);
          const accessibleName = summary === kindLabel ? kindLabel : `${kindLabel} — ${summary}`;
          return (
            <li key={ev.id} className="shrink-0 snap-start">
              <Link
                href={href}
                aria-label={accessibleName}
                data-testid={`recent-activity-card-${ev.id}`}
                className="border-border bg-paper-50 hover:bg-paper-100 flex h-full w-64 flex-col gap-1 rounded-lg border p-3 text-left transition-colors"
              >
                <div className="text-ink-600 flex items-center gap-2 text-xs">
                  <Icon className="size-3.5" aria-hidden />
                  <span className="font-medium">{kindLabel}</span>
                </div>
                <p className="text-ink-800 line-clamp-2 text-sm">{summary}</p>
                <TimestampLabel value={ev.occurred_at} className="text-ink-500 mt-auto" />
              </Link>
            </li>
          );
        })}
      </ol>
    </section>
  );
}
