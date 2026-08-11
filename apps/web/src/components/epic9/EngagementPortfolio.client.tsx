"use client";

import Link from "next/link";
import * as React from "react";

import { TimestampLabel } from "@/components/common/TimestampLabel.client";
import type { EngagementListRow } from "@/lib/bff/engagement-types";
import { readStrategistBffErrorDescription } from "@/lib/bff/read-strategist-bff-error";
import { initialsFor } from "@/lib/labels";

const PHASE_LABEL: Record<string, string> = {
  P1_pre_engagement: "Pre-engagement",
  P2_discovery: "Discovery",
  P3_ecosystem_mapping: "Ecosystem mapping",
  P4_design: "Design",
  P5_pilot: "Pilot",
  P6_scale: "Scale",
  P7_inheritance: "Inheritance",
};

/**
 * Wave 2.5 U7 — the deals table, ranked by attention.
 *
 * Rows are sorted by `attention_score` descending (additive backend field;
 * rows without it sort by recency) and each row shows needs-attention chips
 * (pending proposals, open escalations, days silent) so the portfolio reads
 * as a worklist, not an inventory.
 */
export function EngagementPortfolio() {
  const [engagements, setEngagements] = React.useState<EngagementListRow[]>([]);
  const [err, setErr] = React.useState<string | null>(null);
  const [loading, setLoading] = React.useState(true);

  const refresh = React.useCallback(async () => {
    const r = await fetch("/api/bff/engagements", { cache: "no-store" });
    if (!r.ok) {
      setErr(await readStrategistBffErrorDescription(r));
      return;
    }
    setErr(null);
    const j = (await r.json()) as { engagements?: EngagementListRow[] };
    setEngagements(j.engagements ?? []);
  }, []);

  React.useEffect(() => {
    const t = window.setTimeout(() => {
      refresh()
        .catch((e) => {
          setErr(e instanceof Error ? e.message : "Could not load engagements.");
        })
        .finally(() => setLoading(false));
    }, 0);
    return () => window.clearTimeout(t);
  }, [refresh]);

  const ranked = React.useMemo(() => {
    return [...engagements].sort((a, b) => {
      const scoreDiff = (b.attention_score ?? 0) - (a.attention_score ?? 0);
      if (scoreDiff !== 0) return scoreDiff;
      return Date.parse(b.updated_at) - Date.parse(a.updated_at);
    });
  }, [engagements]);

  return (
    <div className="max-w-5xl space-y-4">
      <div>
        <h1 className="text-display text-ink-950 font-semibold tracking-tight">Engagements</h1>
        <p className="text-body text-ink-600 mt-1 max-w-2xl">
          Your deals, ranked by what needs attention — pending proposals, open escalations, and
          silence float a deal to the top.
        </p>
      </div>
      {err ? <p className="text-sm text-red-ink">{err}</p> : null}
      <div className="overflow-x-auto rounded-card bg-surface shadow-card">
        <table className="w-full min-w-[46rem] text-left text-sm">
          <thead className="text-xs text-ink-600">
            <tr className="border-b border-line">
              <th className="px-3 py-2.5 font-medium">Engagement</th>
              <th className="px-3 py-2.5 font-medium">Needs attention</th>
              <th className="px-3 py-2.5 font-medium">Customer</th>
              <th className="px-3 py-2.5 font-medium">Phase</th>
              <th className="px-3 py-2.5 font-medium">Status</th>
              <th className="px-3 py-2.5 font-medium">Updated</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr>
                <td className="px-3 py-6 text-ink-600" colSpan={6} aria-live="polite">
                  Loading engagements…
                </td>
              </tr>
            ) : ranked.length === 0 ? (
              <tr>
                <td className="px-3 py-6 text-ink-600" colSpan={6}>
                  No engagements yet — run the onboarding wizard to seed your first deal, or create
                  one via the control-plane engagements API (POST /internal/v1/engagements).
                </td>
              </tr>
            ) : (
              ranked.map((e) => (
                <tr
                  key={e.id}
                  className="border-t border-line transition-colors first:border-t-0 hover:bg-hover"
                >
                  <td className="px-3 py-2.5 font-medium">
                    <Link
                      href={`/engagements/${encodeURIComponent(e.id)}`}
                      className="group inline-flex items-center gap-2.5 text-ink underline-offset-2 hover:underline"
                    >
                      <span
                        aria-hidden="true"
                        className="flex size-6 shrink-0 items-center justify-center rounded-full bg-hover-2 text-[10px] font-semibold text-ink-600 shadow-hairline"
                      >
                        {initialsFor(e.name)}
                      </span>
                      {e.name}
                    </Link>
                  </td>
                  <td className="px-3 py-2.5">
                    <NeedsAttentionChips row={e} />
                  </td>
                  <td className="px-3 py-2.5 text-ink-600">{e.customer_account ?? "—"}</td>
                  <td className="px-3 py-2.5">
                    <span className="inline-flex rounded-full bg-hover px-2 py-0.5 text-xs text-ink-600 shadow-hairline">
                      {PHASE_LABEL[e.current_phase] ?? e.current_phase}
                    </span>
                  </td>
                  <td className="px-3 py-2.5">
                    <span
                      className={
                        e.status === "active"
                          ? "inline-flex rounded-full bg-green-tint px-2 py-0.5 text-xs font-medium text-green-ink shadow-hairline"
                          : "inline-flex rounded-full bg-red-tint px-2 py-0.5 text-xs font-medium text-red-ink shadow-hairline"
                      }
                    >
                      {e.status}
                    </span>
                  </td>
                  <td className="px-3 py-2.5 text-xs text-ink-600">
                    <TimestampLabel value={e.updated_at} />
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function NeedsAttentionChips({ row }: { row: EngagementListRow }) {
  const na = row.needs_attention;
  if (!na) {
    // Additive backend field — older CP builds omit it.
    return <span className="text-ink-500 text-xs">—</span>;
  }
  const chips: Array<{ key: string; label: string; tone: "warn" | "quiet" }> = [];
  if (na.proposals_pending > 0) {
    chips.push({
      key: "proposals",
      label: `${na.proposals_pending} proposal${na.proposals_pending === 1 ? "" : "s"}`,
      tone: "warn",
    });
  }
  if (na.escalations_open > 0) {
    chips.push({
      key: "escalations",
      label: `${na.escalations_open} escalation${na.escalations_open === 1 ? "" : "s"}`,
      tone: "warn",
    });
  }
  if (na.days_since_last_event >= 7) {
    chips.push({
      key: "silence",
      label: `${na.days_since_last_event}d silent`,
      tone: "quiet",
    });
  }
  if (chips.length === 0) {
    return <span className="text-ink-500 text-xs">Up to date</span>;
  }
  return (
    <ul className="flex flex-wrap gap-1" data-testid={`needs-attention-${row.id}`}>
      {chips.map((c) => (
        <li
          key={c.key}
          className={
            c.tone === "warn"
              ? "inline-flex rounded-full bg-orange-tint px-2 py-0.5 text-xs font-medium text-orange-ink shadow-hairline"
              : "inline-flex rounded-full bg-hover px-2 py-0.5 text-xs text-ink-600 shadow-hairline"
          }
        >
          {c.label}
        </li>
      ))}
    </ul>
  );
}
