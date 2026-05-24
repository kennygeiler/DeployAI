"use client";

import Link from "next/link";
import * as React from "react";
import { toast } from "sonner";

import { CitationPanel } from "@/components/epic9/CitationPanel.client";
import { EngagementInsights } from "@/components/epic9/EngagementInsights.client";
import { EngagementTimeline } from "@/components/epic9/EngagementTimeline.client";
import { InteractionImport } from "@/components/epic9/InteractionImport.client";
import { MatrixCapture } from "@/components/epic9/MatrixCapture.client";
import { MatrixGraph } from "@/components/epic9/MatrixGraph.client";
import { MatrixProposals } from "@/components/epic9/MatrixProposals.client";
import { RecommendationsPanel } from "@/components/epic9/RecommendationsPanel.client";
import { RoleLensFilter } from "@/components/epic9/RoleLensFilter.client";
import { Button } from "@/components/ui/button";
import type { Engagement, EngagementMember } from "@/lib/bff/engagement-types";
import type { MatrixEdge, MatrixNode, MatrixProposal } from "@/lib/bff/matrix-types";
import { readStrategistBffErrorDescription } from "@/lib/bff/read-strategist-bff-error";
import type { MemberRolesRead } from "@/lib/internal/member-roles-cp";
import { applyRoleLens, type RoleLens } from "@/lib/matrix/role-lens";

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

const MATRIX_NODE_TYPES = [
  "stakeholder",
  "organization",
  "system",
  "decision",
  "risk",
  "commitment",
  "opportunity",
] as const;

const NODE_TYPE_LABEL: Record<string, string> = {
  stakeholder: "Stakeholders",
  organization: "Organizations",
  system: "Systems",
  decision: "Decisions",
  risk: "Risks",
  commitment: "Commitments",
  opportunity: "Opportunities",
};

type DetailResponse = {
  engagement: Engagement;
  members: EngagementMember[];
  matrix?: {
    nodes: MatrixNode[];
    edges: MatrixEdge[];
    proposals?: MatrixProposal[];
  };
};

/**
 * Engagement detail — one customer deployment: its team and the deployment
 * matrix (typed nodes + edges). The Phase 3 engagement-log surfaces — Log,
 * Cross-role view, role lens — were retired in increment 5.5 along with the
 * `engagement_log_entries` journal; the matrix supersedes them.
 */
export function EngagementDetail({ engagementId }: { engagementId: string }) {
  const [data, setData] = React.useState<DetailResponse | null>(null);
  const [err, setErr] = React.useState<string | null>(null);
  const [newUserId, setNewUserId] = React.useState("");
  const [newRole, setNewRole] = React.useState<string>("fde");
  const [busy, setBusy] = React.useState(false);
  const [memberRoles, setMemberRoles] = React.useState<MemberRolesRead | null>(null);

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
    const t = window.setTimeout(() => {
      // Catch low-level fetch failures (network, AbortError on unmount, test
      // teardown leaks) so they don't surface as unhandled rejections.
      // Real BFF errors hit the !r.ok branch inside refresh().
      refresh().catch((e) => {
        setErr(e instanceof Error ? e.message : "Could not load engagement.");
      });
    }, 0);
    return () => window.clearTimeout(t);
  }, [refresh]);

  React.useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const r = await fetch("/api/bff/tenant/member-roles", { cache: "no-store" });
        if (!r.ok) return;
        const body = (await r.json()) as MemberRolesRead;
        if (cancelled) return;
        if (Array.isArray(body?.builtin) && Array.isArray(body?.custom)) {
          setMemberRoles(body);
        }
      } catch {
        // Non-fatal — member-add falls back to the built-in trio.
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const memberRoleOptions = React.useMemo(() => {
    if (memberRoles) {
      return [...memberRoles.builtin, ...memberRoles.custom];
    }
    return [
      { name: "fde", label: "Forward-deployed engineer" },
      { name: "deployment_strategist", label: "Deployment strategist" },
      { name: "biz_dev", label: "Business development" },
    ];
  }, [memberRoles]);
  const memberRoleLabel = React.useCallback(
    (name: string) => {
      const direct = ROLE_LABEL[name];
      if (direct) return direct;
      const custom = memberRoles?.custom.find((c) => c.name === name);
      return custom?.label ?? name;
    },
    [memberRoles],
  );

  const addMember = React.useCallback(async () => {
    const userId = newUserId.trim();
    if (!userId) {
      return;
    }
    setBusy(true);
    try {
      const r = await fetch(`/api/bff/engagements/${encodeURIComponent(engagementId)}/members`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ user_id: userId, role: newRole }),
      });
      if (!r.ok) {
        toast.error("Could not assign member", {
          description: (await readStrategistBffErrorDescription(r)).slice(0, 240),
        });
        return;
      }
      toast.success("Member assigned");
      setNewUserId("");
      await refresh();
    } finally {
      setBusy(false);
    }
  }, [engagementId, newRole, newUserId, refresh]);

  const removeMember = React.useCallback(
    async (memberId: string) => {
      setBusy(true);
      try {
        const r = await fetch(
          `/api/bff/engagements/${encodeURIComponent(engagementId)}/members/` +
            encodeURIComponent(memberId),
          { method: "DELETE" },
        );
        if (!r.ok) {
          toast.error("Could not remove member", {
            description: (await readStrategistBffErrorDescription(r)).slice(0, 240),
          });
          return;
        }
        toast.success("Member removed");
        await refresh();
      } finally {
        setBusy(false);
      }
    },
    [engagementId, refresh],
  );

  const allMatrixNodes = React.useMemo(() => data?.matrix?.nodes ?? [], [data]);
  const allMatrixEdges = React.useMemo(() => data?.matrix?.edges ?? [], [data]);
  const matrixProposals = data?.matrix?.proposals ?? [];
  // Sprint 2 inc 1 — view toggle. Defaults to table (the old surface) so
  // returning users see the familiar shape; graph is one click away.
  const [matrixView, setMatrixView] = React.useState<"table" | "graph">("table");
  const [roleLens, setRoleLens] = React.useState<RoleLens>("all");
  const [citation, setCitation] = React.useState<{
    open: boolean;
    title: string;
    ids: string[];
  }>({ open: false, title: "", ids: [] });
  const openCitation = React.useCallback((node: MatrixNode) => {
    setCitation({
      open: true,
      title: node.title,
      ids: node.evidence_event_ids ?? [],
    });
  }, []);
  const closeCitation = React.useCallback(() => {
    setCitation((c) => ({ ...c, open: false }));
  }, []);
  const { nodes: matrixNodes, edges: matrixEdges } = React.useMemo(
    () => applyRoleLens(allMatrixNodes, allMatrixEdges, roleLens),
    [allMatrixNodes, allMatrixEdges, roleLens],
  );
  const nodeTitleById = new Map(matrixNodes.map((n) => [n.id, n.title] as const));

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
              <p className="text-ink-600 text-sm">No members assigned yet.</p>
            ) : (
              <ul className="border-border divide-border divide-y rounded-lg border text-sm">
                {data.members.map((m) => (
                  <li key={m.id} className="flex items-center justify-between gap-3 px-3 py-2">
                    <span className="font-mono text-xs">{m.user_id}</span>
                    <div className="flex items-center gap-3">
                      <span className="text-ink-700">{memberRoleLabel(m.role)}</span>
                      <Button
                        type="button"
                        variant="outline"
                        size="sm"
                        className="h-7 px-2 text-xs"
                        disabled={busy}
                        onClick={() => void removeMember(m.id)}
                      >
                        Remove
                      </Button>
                    </div>
                  </li>
                ))}
              </ul>
            )}
            <div className="border-border space-y-2 rounded-lg border p-3">
              <h3 className="text-ink-800 text-xs font-semibold">Assign a member</h3>
              <div className="flex flex-wrap items-end gap-2">
                <div className="grid gap-1">
                  <label className="text-ink-600 text-xs" htmlFor="member-user-id">
                    User ID
                  </label>
                  <input
                    id="member-user-id"
                    className="border-border rounded-md border px-2 py-1 text-sm"
                    placeholder="user UUID"
                    value={newUserId}
                    onChange={(e) => setNewUserId(e.target.value)}
                  />
                </div>
                <div className="grid gap-1">
                  <label className="text-ink-600 text-xs" htmlFor="member-role">
                    Role
                  </label>
                  <select
                    id="member-role"
                    className="border-border rounded-md border px-2 py-1 text-sm"
                    value={newRole}
                    onChange={(e) => setNewRole(e.target.value)}
                  >
                    {memberRoleOptions.map((r) => (
                      <option key={r.name} value={r.name}>
                        {r.label}
                      </option>
                    ))}
                  </select>
                </div>
                <Button
                  type="button"
                  size="sm"
                  disabled={busy || !newUserId.trim()}
                  onClick={() => void addMember()}
                >
                  Assign
                </Button>
              </div>
            </div>
          </section>

          <EngagementInsights engagementId={engagementId} />

          <EngagementTimeline engagementId={engagementId} />

          <RecommendationsPanel engagementId={engagementId} />

          <section className="space-y-2">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <h2 className="text-ink-800 text-sm font-semibold">Deployment matrix</h2>
              <div className="flex flex-wrap items-center gap-3">
                <RoleLensFilter value={roleLens} onChange={setRoleLens} />
                <div className="inline-flex gap-1" role="group" aria-label="Matrix view mode">
                  <Button
                    type="button"
                    size="sm"
                    variant={matrixView === "table" ? "default" : "outline"}
                    aria-pressed={matrixView === "table"}
                    onClick={() => setMatrixView("table")}
                    className="h-7 px-3 text-xs"
                  >
                    Table
                  </Button>
                  <Button
                    type="button"
                    size="sm"
                    variant={matrixView === "graph" ? "default" : "outline"}
                    aria-pressed={matrixView === "graph"}
                    onClick={() => setMatrixView("graph")}
                    className="h-7 px-3 text-xs"
                  >
                    Graph
                  </Button>
                </div>
              </div>
            </div>
            {matrixView === "graph" ? (
              <MatrixGraph nodes={matrixNodes} edges={matrixEdges} onNodeClick={openCitation} />
            ) : matrixNodes.length === 0 ? (
              roleLens !== "all" && allMatrixNodes.length > 0 ? (
                <p className="text-ink-600 text-sm">
                  No matrix entities visible for the {ROLE_LABEL[roleLens] ?? roleLens} lens —
                  switch to All or pick a different role.
                </p>
              ) : (
                <p className="text-ink-600 text-sm">
                  No matrix entities yet — add the first one below, or let ingestion (Phase 6)
                  populate the map.
                </p>
              )
            ) : (
              <div className="space-y-3">
                {MATRIX_NODE_TYPES.map((t) => {
                  const nodes = matrixNodes.filter((n) => n.node_type === t);
                  if (nodes.length === 0) {
                    return null;
                  }
                  return (
                    <div key={t} className="space-y-1">
                      <h3 className="text-ink-700 text-xs font-semibold uppercase">
                        {NODE_TYPE_LABEL[t]}
                      </h3>
                      <ul className="border-border divide-border divide-y rounded-lg border text-sm">
                        {nodes.map((n) => {
                          const edges = matrixEdges.filter((e) => e.from_node_id === n.id);
                          return (
                            <li key={n.id} className="space-y-1 px-3 py-2">
                              <div className="flex items-center justify-between gap-3">
                                <span className="text-ink-800 font-medium">{n.title}</span>
                                {n.status ? (
                                  <span className="text-ink-500 text-xs">{n.status}</span>
                                ) : null}
                              </div>
                              {edges.map((e) => (
                                <p key={e.id} className="text-ink-500 text-xs">
                                  {e.edge_type.replace("_", " ")} →{" "}
                                  {nodeTitleById.get(e.to_node_id) ?? "—"}
                                </p>
                              ))}
                            </li>
                          );
                        })}
                      </ul>
                    </div>
                  );
                })}
              </div>
            )}
            <MatrixCapture engagementId={engagementId} nodes={allMatrixNodes} onChanged={refresh} />
            <CitationPanel
              engagementId={engagementId}
              ids={citation.ids}
              title={citation.title}
              open={citation.open}
              onClose={closeCitation}
            />
          </section>

          <section className="space-y-2">
            <h2 className="text-ink-800 text-sm font-semibold">Proposals to review</h2>
            <MatrixProposals
              engagementId={engagementId}
              proposals={matrixProposals}
              nodes={allMatrixNodes}
              onChanged={refresh}
            />
          </section>

          <section className="space-y-2">
            <h2 className="text-ink-800 text-sm font-semibold">Interactions</h2>
            <p className="text-ink-600 text-sm">
              Drop an email, a meeting summary, a field note — or anything else that happened on
              this deployment. Each import is captured as a canonical event; the matrix grows from
              it in Phase 6.2 (extraction).
            </p>
            <InteractionImport engagementId={engagementId} onChanged={refresh} />
          </section>
        </>
      ) : null}
    </div>
  );
}
