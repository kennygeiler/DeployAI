"use client";

import * as React from "react";

import {
  ProvenanceTree,
  type ProvenanceChain,
} from "@/components/engagements/ProvenanceTree.client";
import { readStrategistBffErrorDescription } from "@/lib/bff/read-strategist-bff-error";

async function findRootEventIdForNode(
  engagementId: string,
  nodeId: string,
): Promise<string | null> {
  const url =
    `/api/bff/engagements/${encodeURIComponent(engagementId)}/ledger` +
    `?source_kind=matrix_node_created,matrix_node_updated&limit=500`;
  const r = await fetch(url, { cache: "no-store" });
  if (!r.ok) {
    throw new Error(await readStrategistBffErrorDescription(r));
  }
  const body = (await r.json()) as {
    events?: Array<{ id: string; source_ref: string | null; occurred_at: string }>;
  };
  const events = Array.isArray(body.events) ? body.events : [];
  const matches = events
    .filter((ev) => ev.source_ref === nodeId)
    .sort((a, b) => b.occurred_at.localeCompare(a.occurred_at));
  return matches[0]?.id ?? null;
}

async function findProvenanceNarrative(
  engagementId: string,
  nodeId: string,
): Promise<string | null> {
  const url = `/api/bff/engagements/${encodeURIComponent(engagementId)}/insights` + `?status=open`;
  try {
    const r = await fetch(url, { cache: "no-store" });
    if (!r.ok) return null;
    const body = (await r.json()) as {
      insights?: Array<{
        insight_type?: string;
        body?: string;
        citation_node_ids?: string[];
      }>;
    };
    const list = Array.isArray(body.insights) ? body.insights : [];
    const hit = list.find(
      (i) =>
        i.insight_type === "decision_provenance_summary" &&
        Array.isArray(i.citation_node_ids) &&
        i.citation_node_ids.includes(nodeId),
    );
    return hit?.body ?? null;
  } catch {
    return null;
  }
}

export function ProvenanceTab({
  engagementId,
  nodeId,
  active,
}: {
  engagementId: string;
  nodeId: string;
  active: boolean;
}) {
  const [chain, setChain] = React.useState<ProvenanceChain | null>(null);
  const [narrative, setNarrative] = React.useState<string | null>(null);
  const [loading, setLoading] = React.useState(false);
  const [err, setErr] = React.useState<string | null>(null);
  const [emptyReason, setEmptyReason] = React.useState<string | null>(null);

  React.useEffect(() => {
    if (!active) return;
    let cancelled = false;
    void (async () => {
      setLoading(true);
      setErr(null);
      setEmptyReason(null);
      setChain(null);
      setNarrative(null);
      try {
        const rootEventId = await findRootEventIdForNode(engagementId, nodeId);
        if (cancelled) return;
        if (!rootEventId) {
          setEmptyReason("No ledger event found for this node yet.");
          return;
        }
        const chainUrl =
          `/api/bff/engagements/${encodeURIComponent(engagementId)}/ledger/chain/` +
          `${encodeURIComponent(rootEventId)}`;
        const r = await fetch(chainUrl, { cache: "no-store" });
        if (cancelled) return;
        if (!r.ok) {
          setErr(await readStrategistBffErrorDescription(r));
          return;
        }
        const body = (await r.json()) as ProvenanceChain;
        setChain(body);
        const narrativeBody = await findProvenanceNarrative(engagementId, nodeId);
        if (cancelled) return;
        setNarrative(narrativeBody);
      } catch (e) {
        if (!cancelled) {
          setErr(e instanceof Error ? e.message : "Could not load provenance.");
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [active, engagementId, nodeId]);

  if (!active) return null;
  return (
    <div className="space-y-3">
      {narrative ? (
        <section
          aria-label="Decision provenance summary"
          className="bg-ink-50 border-border space-y-1 rounded-lg border p-3"
        >
          <p className="text-warning-900 bg-warning-100 inline-block rounded px-1.5 py-0.5 text-[10px] uppercase">
            AI-generated draft
          </p>
          <p className="text-ink-800 text-sm whitespace-pre-line">{narrative}</p>
        </section>
      ) : null}
      {err ? <p className="text-error-700 text-sm">{err}</p> : null}
      {loading ? (
        <p className="text-ink-600 text-sm">Loading provenance…</p>
      ) : emptyReason ? (
        <p className="text-ink-600 text-sm">{emptyReason}</p>
      ) : chain ? (
        <ProvenanceTree chain={chain} />
      ) : null}
    </div>
  );
}
