"use client";

import Link from "next/link";
import * as React from "react";

import { TimestampLabel } from "@/components/common/TimestampLabel.client";
import type { Engagement } from "@/lib/bff/engagement-types";
import { readStrategistBffErrorDescription } from "@/lib/bff/read-strategist-bff-error";

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
 * Phase 3 — the "my engagements" portfolio. Lists every engagement for the
 * team with its phase and status; non-active engagements are flagged.
 */
export function EngagementPortfolio() {
  const [engagements, setEngagements] = React.useState<Engagement[]>([]);
  const [err, setErr] = React.useState<string | null>(null);
  const [loading, setLoading] = React.useState(true);

  const refresh = React.useCallback(async () => {
    const r = await fetch("/api/bff/engagements", { cache: "no-store" });
    if (!r.ok) {
      setErr(await readStrategistBffErrorDescription(r));
      return;
    }
    setErr(null);
    const j = (await r.json()) as { engagements?: Engagement[] };
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

  return (
    <div className="max-w-5xl space-y-4">
      <div>
        <h1 className="text-display text-ink-950 font-semibold tracking-tight">Engagements</h1>
        <p className="text-body text-ink-600 mt-1 max-w-2xl">
          Your team&apos;s portfolio — every customer deployment, its phase, and its status.
        </p>
      </div>
      {err ? <p className="text-sm text-red-ink">{err}</p> : null}
      {/* Records Table — Beautiful UI component 12: surface card, hairline
          rows, avatar initials, tag chips, relative last-interaction. */}
      <div className="overflow-x-auto rounded-card bg-surface shadow-card">
        <table className="w-full min-w-[40rem] text-left text-sm">
          <thead className="text-xs text-ink-600">
            <tr className="border-b border-line">
              <th className="px-3 py-2.5 font-medium">Engagement</th>
              <th className="px-3 py-2.5 font-medium">Customer</th>
              <th className="px-3 py-2.5 font-medium">Phase</th>
              <th className="px-3 py-2.5 font-medium">Status</th>
              <th className="px-3 py-2.5 font-medium">Updated</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr>
                <td className="px-3 py-6 text-ink-600" colSpan={5} aria-live="polite">
                  Loading engagements…
                </td>
              </tr>
            ) : engagements.length === 0 ? (
              <tr>
                <td className="px-3 py-6 text-ink-600" colSpan={5}>
                  No engagements yet — create one via the control-plane engagements API (POST
                  /internal/v1/engagements).
                </td>
              </tr>
            ) : (
              engagements.map((e) => (
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
                        {e.name.slice(0, 1).toUpperCase()}
                      </span>
                      {e.name}
                    </Link>
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
