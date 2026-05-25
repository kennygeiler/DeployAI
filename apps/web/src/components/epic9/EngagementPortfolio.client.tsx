"use client";

import Link from "next/link";
import * as React from "react";

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
      {err ? <p className="text-destructive text-sm">{err}</p> : null}
      <div className="border-border overflow-x-auto rounded-lg border">
        <table className="w-full min-w-[40rem] text-left text-sm">
          <thead className="bg-paper-200/80 text-ink-700">
            <tr>
              <th className="px-3 py-2 font-medium">Engagement</th>
              <th className="px-3 py-2 font-medium">Customer</th>
              <th className="px-3 py-2 font-medium">Phase</th>
              <th className="px-3 py-2 font-medium">Status</th>
              <th className="px-3 py-2 font-medium">Updated</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr>
                <td className="text-ink-600 px-3 py-6" colSpan={5} aria-live="polite">
                  Loading engagements…
                </td>
              </tr>
            ) : engagements.length === 0 ? (
              <tr>
                <td className="text-ink-600 px-3 py-6" colSpan={5}>
                  No engagements yet — create one via the control-plane engagements API (POST
                  /internal/v1/engagements).
                </td>
              </tr>
            ) : (
              engagements.map((e) => (
                <tr key={e.id} className="border-border border-t">
                  <td className="px-3 py-2 font-medium">
                    <Link
                      href={`/engagements/${encodeURIComponent(e.id)}`}
                      className="text-evidence-800 underline-offset-2 hover:underline"
                    >
                      {e.name}
                    </Link>
                  </td>
                  <td className="text-ink-600 px-3 py-2">{e.customer_account ?? "—"}</td>
                  <td className="px-3 py-2">{PHASE_LABEL[e.current_phase] ?? e.current_phase}</td>
                  <td className="px-3 py-2">
                    <span
                      className={
                        e.status === "active"
                          ? "text-evidence-800 text-xs font-medium"
                          : "text-destructive text-xs font-medium"
                      }
                    >
                      {e.status}
                    </span>
                  </td>
                  <td className="text-ink-600 px-3 py-2 font-mono text-xs">
                    {e.updated_at.slice(0, 10)}
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
