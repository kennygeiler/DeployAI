import type { Metadata } from "next"
import { notFound } from "next/navigation"

import { decideSync } from "@deployai/authz"

import { getActorFromHeaders } from "@/lib/internal/actor"

import { type RunRow, RunsTable } from "./RunsTable.client"

export const metadata: Metadata = {
  title: "Admin — Ingestion runs",
  description: "Platform Admin cockpit for ingestion runs (Story 1-16).",
}

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
]

export default async function AdminRunsPage() {
  const actor = await getActorFromHeaders()
  if (!actor) {
    notFound()
  }
  const d = decideSync(actor, "ingest:view_runs", { kind: "ingestion_runs" })
  if (!d.allow) {
    notFound()
  }

  return (
    <main id="main" tabIndex={-1} className="mx-auto flex max-w-5xl flex-col gap-6 p-8 outline-none">
      <div>
        <h1 className="text-display font-semibold tracking-tight text-ink-950">Ingestion runs</h1>
        <p className="text-body text-ink-600">
          Recent runs (seed data until Epic 3 lands the real control-plane API).
        </p>
      </div>
      <RunsTable rows={seed} />
    </main>
  )
}
