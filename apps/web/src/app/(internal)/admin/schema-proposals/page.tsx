import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { decideSync } from "@deployai/authz";

import { getActorFromHeaders } from "@/lib/internal/actor";
import { getControlPlaneBaseUrl, getControlPlaneInternalKey } from "@/lib/internal/control-plane";

import { type ProposalRow, SchemaProposalsTable } from "./SchemaProposalsTable.client";

export const metadata: Metadata = {
  title: "Admin — Schema proposals",
  description: "Review Cartographer field proposals (Story 1-17).",
  robots: { index: false, follow: false },
};

export default async function AdminSchemaProposalsPage() {
  const actor = await getActorFromHeaders();
  if (!actor) {
    notFound();
  }
  const d = decideSync(actor, "admin:view_schema_proposals", { kind: "schema_proposals" });
  if (!d.allow) {
    notFound();
  }

  const base = getControlPlaneBaseUrl();
  const key = getControlPlaneInternalKey();
  const cpReady = Boolean(base && key);

  const forwardActor = actor.tenantId ? { role: actor.role, tenantId: actor.tenantId } : null;

  let initialRows: ProposalRow[] = [];
  if (cpReady && base && key && actor.tenantId) {
    const url = `${base.replace(/\/$/, "")}/internal/v1/tenants/${actor.tenantId}/schema-proposals?status=pending`;
    const r = await fetch(url, {
      headers: { "X-DeployAI-Internal-Key": key },
      cache: "no-store",
    });
    if (r.ok) {
      initialRows = (await r.json()) as ProposalRow[];
    }
  }

  return (
    <main className="mx-auto flex max-w-5xl flex-col gap-6 p-8">
      <div>
        <h1 className="text-display font-semibold tracking-tight text-ink-950">Schema proposals</h1>
        <p className="text-body text-ink-600">
          Review pending field proposals. Requires control-plane and server env{" "}
          <code className="text-body bg-paper-200 rounded px-1">DEPLOYAI_CONTROL_PLANE_URL</code> +{" "}
          <code className="text-body bg-paper-200 rounded px-1">DEPLOYAI_INTERNAL_API_KEY</code> on
          the web app.
        </p>
        {!cpReady ? (
          <p className="text-body text-ink-500 mt-2">
            Control plane is not fully configured; the table will show a 503 until the web server
            has a reachable API URL and internal key.
          </p>
        ) : null}
        {!actor.tenantId ? (
          <p className="text-body text-ink-500 mt-2">
            Set the <code className="bg-paper-200 rounded px-1">x-deployai-tenant</code> header to a
            tenant UUID so list and actions are scoped.
          </p>
        ) : null}
      </div>
      <SchemaProposalsTable forwardActor={forwardActor} initialRows={initialRows} />
    </main>
  );
}
