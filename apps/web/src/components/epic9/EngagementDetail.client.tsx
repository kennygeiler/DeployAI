"use client";

import Link from "next/link";
import * as React from "react";

import type { EngagementLogEntry } from "@/lib/bff/engagement-log-types";
import type { Engagement, EngagementMember } from "@/lib/bff/engagement-types";
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

const ROLE_LABEL: Record<string, string> = {
  fde: "Forward-deployed engineer",
  deployment_strategist: "Deployment strategist",
  biz_dev: "Business development",
};

type DetailResponse = {
  engagement: Engagement;
  members: EngagementMember[];
  log: EngagementLogEntry[];
};

/**
 * Phase 4 — engagement detail. One customer deployment with its team and
 * log roll-up. Read-only here; membership mutation lands in increment 4.2.
 */
export function EngagementDetail({ engagementId }: { engagementId: string }) {
  const [data, setData] = React.useState<DetailResponse | null>(null);
  const [err, setErr] = React.useState<string | null>(null);

  const refresh = React.useCallback(async () => {
    const r = await fetch(`/api/bff/engagements/${encodeURIComponent(engagementId)}`, {
      cache: "no-store",
    });
    if (!r.ok) {
      setErr(await readStrategistBffErrorDescription(r));
      setData(null);
      return;
    }
    setErr(null);
    setData((await r.json()) as DetailResponse);
  }, [engagementId]);

  React.useEffect(() => {
    const t = window.setTimeout(() => void refresh(), 0);
    return () => window.clearTimeout(t);
  }, [refresh]);

  return (
    <div className="max-w-5xl space-y-5">
      <Link
        href="/engagements"
        className="text-evidence-800 text-sm font-medium underline-offset-2 hover:underline"
      >
        ← All engagements
      </Link>
      {err ? <p className="text-destructive text-sm">{err}</p> : null}
      {!data && !err ? <p className="text-ink-600 text-sm">Loading…</p> : null}
      {data ? (
        <>
          <header>
            <h1 className="text-display text-ink-950 font-semibold tracking-tight">
              {data.engagement.name}
            </h1>
            <dl className="text-body text-ink-600 mt-2 flex flex-wrap gap-x-6 gap-y-1">
              <div>
                <dt className="sr-only">Customer</dt>
                <dd>Customer: {data.engagement.customer_account ?? "—"}</dd>
              </div>
              <div>
                <dt className="sr-only">Phase</dt>
                <dd>
                  Phase:{" "}
                  {PHASE_LABEL[data.engagement.current_phase] ?? data.engagement.current_phase}
                </dd>
              </div>
              <div>
                <dt className="sr-only">Status</dt>
                <dd>
                  Status:{" "}
                  <span
                    className={
                      data.engagement.status === "active"
                        ? "text-evidence-800 font-medium"
                        : "text-destructive font-medium"
                    }
                  >
                    {data.engagement.status}
                  </span>
                </dd>
              </div>
            </dl>
          </header>

          <section className="space-y-2">
            <h2 className="text-ink-800 text-sm font-semibold">Team</h2>
            {data.members.length === 0 ? (
              <p className="text-ink-600 text-sm">
                No members assigned yet — assignment lands in Phase 4.2.
              </p>
            ) : (
              <ul className="border-border divide-border divide-y rounded-lg border text-sm">
                {data.members.map((m) => (
                  <li key={m.id} className="flex items-center justify-between gap-3 px-3 py-2">
                    <span className="font-mono text-xs">{m.user_id}</span>
                    <span className="text-ink-700">{ROLE_LABEL[m.role] ?? m.role}</span>
                  </li>
                ))}
              </ul>
            )}
          </section>

          <section className="space-y-2">
            <h2 className="text-ink-800 text-sm font-semibold">Log</h2>
            {data.log.length === 0 ? (
              <p className="text-ink-600 text-sm">
                No log entries yet — capture meetings, decisions, risks, and next actions from the
                action queue.
              </p>
            ) : (
              <ul className="border-border divide-border divide-y rounded-lg border text-sm">
                {data.log.map((e) => (
                  <li key={e.id} className="space-y-1 px-3 py-2">
                    <div className="flex items-center justify-between gap-3">
                      <span className="text-ink-600 font-mono text-xs uppercase">
                        {e.entry_kind.replace("_", " ")}
                      </span>
                      <span className="text-ink-500 font-mono text-xs">
                        {e.created_at.slice(0, 10)}
                      </span>
                    </div>
                    <p className="text-ink-700">{e.body}</p>
                    {e.author ? <p className="text-ink-500 text-xs">— {e.author}</p> : null}
                  </li>
                ))}
              </ul>
            )}
          </section>
        </>
      ) : null}
    </div>
  );
}
