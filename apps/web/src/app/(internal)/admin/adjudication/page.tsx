import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { decideSync } from "@deployai/authz";

import { getActorFromHeaders } from "@/lib/internal/actor";
import { getControlPlaneBaseUrl, getControlPlaneInternalKey } from "@/lib/internal/control-plane";

import { AdjudicationTable, type AdjudicationRow } from "./AdjudicationTable.client";

export const metadata: Metadata = {
  title: "Admin — Adjudication queue",
  description: "Human review of replay-parity and citation disagreements (Epic 4, Story 4-7).",
};

export default async function AdminAdjudicationPage() {
  const actor = await getActorFromHeaders();
  if (!actor) {
    notFound();
  }
  const d = decideSync(actor, "eval:view_adjudication", { kind: "global" });
  if (!d.allow) {
    notFound();
  }

  const base = getControlPlaneBaseUrl();
  const key = getControlPlaneInternalKey();
  const cpReady = Boolean(base && key);

  let initialRows: AdjudicationRow[] = [];
  if (cpReady && base && key) {
    const r = await fetch(
      `${base.replace(/\/$/, "")}/internal/v1/adjudication-queue-items?limit=200`,
      {
        headers: { "X-DeployAI-Internal-Key": key },
        cache: "no-store",
      },
    );
    if (r.ok) {
      const j = (await r.json()) as Array<{
        id: string;
        tenant_id: string;
        query_id: string;
        status: string;
        created_at: string;
        meta: Record<string, unknown>;
      }>;
      initialRows = j.map((x) => ({
        id: x.id,
        tenant: x.tenant_id,
        queryId: x.query_id,
        status: x.status,
        createdAt: x.created_at,
        raw: { ...x.meta },
      }));
    }
  }

  return (
    <main
      id="main"
      tabIndex={-1}
      className="mx-auto flex max-w-5xl flex-col gap-6 p-8 outline-none"
    >
      <div>
        <h1 className="text-display font-semibold tracking-tight text-ink-950">Adjudication</h1>
        <p className="text-body text-ink-600 max-w-2xl">
          Queue for human decisions when rule-based and LLM-judge evaluators disagree. Rows come
          from the control plane when{" "}
          <code className="text-body bg-paper-200 rounded px-1">DEPLOYAI_CONTROL_PLANE_URL</code>{" "}
          and <code className="text-body bg-paper-200 rounded px-1">DEPLOYAI_INTERNAL_API_KEY</code>{" "}
          are set.
        </p>
        {!cpReady ? (
          <p className="text-body text-ink-500 mt-2">
            Configure the control plane URL and internal key to load the adjudication queue.
          </p>
        ) : null}
      </div>
      <AdjudicationTable rows={initialRows} />
    </main>
  );
}
