"use client";

import {
  CalendarIcon,
  ClipboardListIcon,
  FileTextIcon,
  GitBranchIcon,
  LightbulbIcon,
  MailIcon,
  ShieldCheckIcon,
  SparklesIcon,
  UserPlusIcon,
} from "lucide-react";
import Link from "next/link";
import * as React from "react";

import { TimestampLabel } from "@/components/common/TimestampLabel.client";
import { readStrategistBffErrorDescription } from "@/lib/bff/read-strategist-bff-error";
import type { LedgerEvent } from "@/lib/internal/ledger-cp";

type IconComponent = React.ComponentType<{ className?: string; "aria-hidden"?: boolean }>;

const SOURCE_KIND_ICON: Record<string, IconComponent> = {
  email_ingest: MailIcon,
  meeting_webhook: CalendarIcon,
  manual_capture: ClipboardListIcon,
  llm_proposal_created: SparklesIcon,
  proposal_accepted: SparklesIcon,
  proposal_rejected: SparklesIcon,
  matrix_node_created: GitBranchIcon,
  matrix_node_updated: GitBranchIcon,
  matrix_node_deleted: GitBranchIcon,
  matrix_edge_created: GitBranchIcon,
  matrix_edge_deleted: GitBranchIcon,
  insight_opened: LightbulbIcon,
  insight_closed: LightbulbIcon,
  recommendation_emitted: LightbulbIcon,
  recommendation_actioned: LightbulbIcon,
  engagement_phase_change: ShieldCheckIcon,
  member_added: UserPlusIcon,
  member_removed: UserPlusIcon,
  settings_change: ShieldCheckIcon,
  audit_other: ShieldCheckIcon,
  audit_decision: ShieldCheckIcon,
  user_provisioned: UserPlusIcon,
};

function iconFor(sourceKind: string): IconComponent {
  return SOURCE_KIND_ICON[sourceKind] ?? FileTextIcon;
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
        <p role="alert" className="text-error-700 text-sm">
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
          const accessibleName = `${ev.source_kind.replace(/_/g, " ")} — ${ev.summary}`;
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
                  <span className="font-mono uppercase">{ev.source_kind}</span>
                </div>
                <p className="text-ink-800 line-clamp-2 text-sm">{ev.summary}</p>
                <TimestampLabel value={ev.occurred_at} className="text-ink-500 mt-auto" />
              </Link>
            </li>
          );
        })}
      </ol>
    </section>
  );
}
