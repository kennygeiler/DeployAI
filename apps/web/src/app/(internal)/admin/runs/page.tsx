import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { decideSync } from "@deployai/authz";

import { getActorFromHeaders } from "@/lib/internal/actor";
import { getControlPlaneBaseUrl, getControlPlaneInternalKey } from "@/lib/internal/control-plane";

import { type RunRow, RunsTable } from "./RunsTable.client";

export const metadata: Metadata = {
  title: "Admin — Ingestion runs",
  description: "Platform Admin cockpit for ingestion runs (Story 1-16).",
};

type CpIngestionRun = {
  id: string;
  tenant_id: string;
  integration: string;
  started_at: string;
  completed_at: string | null;
  status: string;
  events_written: number;
  error_count: number;
  error_summary: Record<string, unknown>;
  meta: Record<string, unknown>;
};

const seed: RunRow[] = [
  {
    id: "run-001",
    tenant: "tenant-a",
    source: "m365-calendar",
    startedAt: "2026-04-20T14:00:00.000Z",
    status: "succeeded",
    eventCount: 128,
    raw: { run: "run-001", region: "us-east-1" },
  },
  {
    id: "run-002",
    tenant: "tenant-b",
    source: "exchange-mail",
    startedAt: "2026-04-21T09:15:00.000Z",
    status: "running",
    eventCount: 42,
    raw: { run: "run-002", cursor: "opaque" },
  },
];

export default async function AdminRunsPage() {
  const actor = await getActorFromHeaders();
  if (!actor) {
    notFound();
  }
  const d = decideSync(actor, "ingest:view_runs", { kind: "ingestion_runs" });
  if (!d.allow) {
    notFound();
  }

  const base = getControlPlaneBaseUrl();
  const key = getControlPlaneInternalKey();
  const cpReady = Boolean(base && key);

  let initialRows: RunRow[] = seed;
  if (cpReady && base && key) {
    const r = await fetch(`${base.replace(/\/$/, "")}/internal/v1/ingestion-runs?limit=100`, {
      headers: { "X-DeployAI-Internal-Key": key },
      cache: "no-store",
    });
    if (r.ok) {
      const j = (await r.json()) as CpIngestionRun[];
      if (j.length > 0) {
        const tracesBase =
          "https://docs.aws.amazon.com/AmazonCloudWatch/latest/logs/WhatIsCloudWatchLogs.html";
        initialRows = j.map((x) => {
          const fromMeta = (x.meta as { observability_traces?: string }).observability_traces;
          return {
            id: x.id,
            tenant: x.tenant_id,
            source: x.integration,
            startedAt: x.started_at,
            status: x.status,
            eventCount: x.events_written,
            raw: {
              error_count: x.error_count,
              error_summary: x.error_summary,
              completed_at: x.completed_at,
              ...x.meta,
              observability_traces: fromMeta ?? tracesBase,
            },
          };
        });
      }
    }
  }

  return (
    <main
      id="main"
      tabIndex={-1}
      className="mx-auto flex max-w-5xl flex-col gap-6 p-8 outline-none"
    >
      <div>
        <h1 className="text-display font-semibold tracking-tight text-ink-950">Ingestion runs</h1>
        <p className="text-body text-ink-600">
          Live data from the control plane when the web server has{" "}
          <code className="text-body bg-paper-200 rounded px-1">DEPLOYAI_CONTROL_PLANE_URL</code>{" "}
          and <code className="text-body bg-paper-200 rounded px-1">DEPLOYAI_INTERNAL_API_KEY</code>{" "}
          set; otherwise the seed preview.
        </p>
        {!cpReady ? (
          <p className="text-body text-ink-500 mt-2">
            Configure the control plane URL and internal key to see real ingestion run rows.
          </p>
        ) : null}
      </div>
      <RunsTable rows={initialRows} />
    </main>
  );
}
