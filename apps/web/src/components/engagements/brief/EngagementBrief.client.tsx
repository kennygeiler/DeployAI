"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import * as React from "react";
import { toast } from "sonner";

import { SectionWithTimeline } from "@/components/common/SectionWithTimeline.client";
import { AskKennyBar } from "@/components/engagements/brief/AskKennyBar.client";
import { DeltaDigest } from "@/components/engagements/brief/DeltaDigest.client";
import { NeedsYou } from "@/components/engagements/brief/NeedsYou.client";
import { MatrixNodeDetail } from "@/components/engagements/MatrixNodeDetail.client";
import { OracleChat } from "@/components/engagements/OracleChat.client";
import { EngagementInsights } from "@/components/epic9/EngagementInsights.client";
import { EngagementTimeline } from "@/components/epic9/EngagementTimeline.client";
import { InteractionImport } from "@/components/epic9/InteractionImport.client";
import { MatrixCapture } from "@/components/epic9/MatrixCapture.client";
import { MatrixGraph } from "@/components/epic9/MatrixGraph.client";
import { RecommendationsPanel } from "@/components/epic9/RecommendationsPanel.client";
import { RoleLensFilter } from "@/components/epic9/RoleLensFilter.client";
import { Button } from "@/components/ui/button";
import { ShimmerLines } from "@/components/ui/shimmer";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import type { Engagement, EngagementMember } from "@/lib/bff/engagement-types";
import type { MatrixEdge, MatrixNode, MatrixProposal } from "@/lib/bff/matrix-types";
import { readStrategistBffErrorDescription } from "@/lib/bff/read-strategist-bff-error";
import type { EngagementSummary, EngagementSummaryCounts } from "@/lib/bff/summary-types";
import type { Section } from "@/lib/bff/temporal-filter";
import { displayNameForPerson, initialsFor } from "@/lib/labels";
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

type MemberRoleOption = { name: string; label: string };

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

const NODE_TYPE_SECTION: Partial<Record<(typeof MATRIX_NODE_TYPES)[number], Section>> = {
  stakeholder: "stakeholders",
  system: "systems",
  decision: "decisions",
  risk: "risks",
  commitment: "commitments",
};

function getNodeTimestamp(n: MatrixNode): string {
  return n.created_at;
}

type CustomNodeTypeFromDetail = {
  name: string;
  label: string;
  color: string | null;
};

type DetailResponse = {
  engagement: Engagement;
  members: EngagementMember[];
  matrix?: {
    nodes: MatrixNode[];
    edges: MatrixEdge[];
    proposals?: MatrixProposal[];
    node_types?: CustomNodeTypeFromDetail[];
  };
};

/**
 * Wave 2.5 U3 — the engagement Brief.
 *
 * Reading order for a deal lead: (1) header with count chips, (2) "Since you
 * last looked" (DeltaDigest — F1's future home), (3) "Needs you" inline
 * action queue, (4) narrative cards (People / Decisions / Risks /
 * Commitments), then insights + recommendations, then tabs for the graph,
 * timeline, people management, and capture. The summary endpoint paints
 * first; the heavy detail aggregate hydrates the rest (U6 makes it lazy).
 *
 * The agent-telemetry activity strip moved to the admin dashboard; team
 * management moved off the top of the page into the People tab.
 */
export function EngagementBrief({ engagementId }: { engagementId: string }) {
  const router = useRouter();

  // Summary — fast first paint. 404 = CP endpoint not deployed; degrade to
  // the full-payload path silently.
  const [summary, setSummary] = React.useState<EngagementSummary | null>(null);
  const [summaryPending, setSummaryPending] = React.useState(true);

  // Detail aggregate — heavy payload (matrix, proposals, member ids).
  const [data, setData] = React.useState<DetailResponse | null>(null);
  const [err, setErr] = React.useState<string | null>(null);

  const [newEmail, setNewEmail] = React.useState("");
  const [newRole, setNewRole] = React.useState<string>("fde");
  const [busy, setBusy] = React.useState(false);
  const [memberRoleOptions, setMemberRoleOptions] = React.useState<MemberRoleOption[]>([
    { name: "fde", label: ROLE_LABEL.fde! },
    { name: "deployment_strategist", label: ROLE_LABEL.deployment_strategist! },
    { name: "biz_dev", label: ROLE_LABEL.biz_dev! },
  ]);

  const refreshSummary = React.useCallback(async () => {
    try {
      const r = await fetch(`/api/bff/engagements/${encodeURIComponent(engagementId)}/summary`, {
        cache: "no-store",
      });
      if (!r.ok) {
        // 404 (endpoint not deployed) or transient error — the detail
        // aggregate covers the header; recent changes stay empty.
        setSummary(null);
        return;
      }
      setSummary((await r.json()) as EngagementSummary);
    } catch {
      setSummary(null);
    } finally {
      setSummaryPending(false);
    }
  }, [engagementId]);

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
      void refreshSummary();
      refresh().catch((e) => {
        setErr(e instanceof Error ? e.message : "Could not load engagement.");
      });
    }, 0);
    return () => window.clearTimeout(t);
  }, [refresh, refreshSummary]);

  React.useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const r = await fetch("/api/bff/tenant/member-roles", { method: "GET" });
        if (!r.ok || cancelled) return;
        const body = (await r.json()) as {
          builtin: MemberRoleOption[];
          custom: MemberRoleOption[];
        };
        if (cancelled) return;
        const merged = [...body.builtin, ...body.custom];
        if (merged.length > 0) {
          setMemberRoleOptions(merged);
        }
      } catch {
        // Builtin defaults remain in state; member-add still works.
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const addMember = React.useCallback(async () => {
    const email = newEmail.trim();
    if (!email) {
      return;
    }
    setBusy(true);
    try {
      const r = await fetch(`/api/bff/engagements/${encodeURIComponent(engagementId)}/members`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ email, role: newRole }),
      });
      if (!r.ok) {
        toast.error("Could not assign member", {
          description: (await readStrategistBffErrorDescription(r)).slice(0, 240),
        });
        return;
      }
      toast.success("Member assigned");
      setNewEmail("");
      await Promise.all([refresh(), refreshSummary()]);
    } finally {
      setBusy(false);
    }
  }, [engagementId, newRole, newEmail, refresh, refreshSummary]);

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
        await Promise.all([refresh(), refreshSummary()]);
      } finally {
        setBusy(false);
      }
    },
    [engagementId, refresh, refreshSummary],
  );

  const allMatrixNodes = React.useMemo(() => data?.matrix?.nodes ?? [], [data]);
  const allMatrixEdges = React.useMemo(() => data?.matrix?.edges ?? [], [data]);
  const matrixProposals = React.useMemo(() => data?.matrix?.proposals ?? [], [data]);

  const [matrixView, setMatrixView] = React.useState<"table" | "graph">("table");
  const [roleLens, setRoleLens] = React.useState<RoleLens>("all");
  const [citation, setCitation] = React.useState<{
    open: boolean;
    title: string;
    ids: string[];
    nodeId: string | null;
  }>({ open: false, title: "", ids: [], nodeId: null });
  const openCitation = React.useCallback((node: MatrixNode) => {
    setCitation({
      open: true,
      title: node.title,
      ids: node.evidence_event_ids ?? [],
      nodeId: node.id,
    });
  }, []);
  const closeCitation = React.useCallback(() => {
    setCitation((c) => ({ ...c, open: false }));
  }, []);
  const handleStakeholderClick = React.useCallback(
    (node: MatrixNode) => {
      router.push(
        `/engagements/${encodeURIComponent(engagementId)}/timeline?timeline.stakeholder=${encodeURIComponent(node.id)}`,
      );
    },
    [router, engagementId],
  );
  const { nodes: matrixNodes, edges: matrixEdges } = React.useMemo(
    () => applyRoleLens(allMatrixNodes, allMatrixEdges, roleLens),
    [allMatrixNodes, allMatrixEdges, roleLens],
  );
  const nodeTitleById = new Map(matrixNodes.map((n) => [n.id, n.title] as const));

  // Header prefers the summary (fast, small); the detail aggregate is the
  // fallback when the summary endpoint is unavailable.
  const header = summary?.engagement ?? data?.engagement ?? null;

  // Count chips: summary counts when present, else derived from the matrix.
  const counts = React.useMemo<EngagementSummaryCounts | null>(() => {
    if (summary) return summary.counts;
    if (!data?.matrix) return null;
    const byType = (t: string) => allMatrixNodes.filter((n) => n.node_type === t).length;
    return {
      stakeholders: byType("stakeholder"),
      decisions: byType("decision"),
      risks_open: allMatrixNodes.filter((n) => n.node_type === "risk" && n.status !== "closed")
        .length,
      commitments: byType("commitment"),
      proposals_pending: matrixProposals.filter((p) => p.status === "pending").length,
      escalations_open: 0,
      disputes_open: 0,
    };
  }, [summary, data, allMatrixNodes, matrixProposals]);

  // Identity lookup for narrative cards: summary members carry names.
  const memberIdentityByUserId = React.useMemo(() => {
    const map = new Map<string, { display_name: string | null; email: string | null }>();
    for (const m of summary?.members ?? []) {
      map.set(m.user_id, { display_name: m.display_name, email: m.email });
    }
    return map;
  }, [summary]);

  const membersForDisplay = React.useMemo(() => {
    return (data?.members ?? []).map((m) => {
      const identity = memberIdentityByUserId.get(m.user_id);
      return {
        ...m,
        display_name: m.display_name ?? identity?.display_name ?? null,
        email: m.email ?? identity?.email ?? null,
      };
    });
  }, [data, memberIdentityByUserId]);

  const stakeholderNodes = allMatrixNodes.filter((n) => n.node_type === "stakeholder");

  return (
    <div className="max-w-5xl space-y-5">
      <Link
        href="/engagements"
        className="text-evidence-800 text-sm font-medium underline-offset-2 hover:underline"
      >
        ← All engagements
      </Link>
      {err ? <p className="text-destructive text-sm">{err}</p> : null}

      {/* 1 — Header: identity + count chips. Shimmer while nothing loaded. */}
      {!header && !err ? (
        <div className="space-y-3" data-testid="brief-header-shimmer">
          <ShimmerLines lines={2} />
        </div>
      ) : null}
      {header ? (
        <header className="space-y-2" data-testid="brief-header">
          <h1 className="text-display text-ink-950 font-semibold tracking-tight">{header.name}</h1>
          <dl className="text-body text-ink-600 flex flex-wrap gap-x-6 gap-y-1">
            <div>
              <dt className="sr-only">Customer</dt>
              <dd>Customer: {header.customer_account ?? "—"}</dd>
            </div>
            <div>
              <dt className="sr-only">Phase</dt>
              <dd>Phase: {PHASE_LABEL[header.current_phase] ?? header.current_phase}</dd>
            </div>
            <div>
              <dt className="sr-only">Status</dt>
              <dd>
                Status:{" "}
                <span
                  className={
                    header.status === "active"
                      ? "inline-flex rounded-full bg-green-tint px-2 py-0.5 text-xs font-medium text-green-ink shadow-hairline"
                      : "inline-flex rounded-full bg-red-tint px-2 py-0.5 text-xs font-medium text-red-ink shadow-hairline"
                  }
                >
                  {header.status}
                </span>
              </dd>
            </div>
          </dl>
          {counts ? (
            <ul className="flex flex-wrap gap-1.5 text-xs" data-testid="brief-count-chips">
              {(
                [
                  ["Stakeholders", counts.stakeholders],
                  ["Decisions", counts.decisions],
                  ["Open risks", counts.risks_open],
                  ["Commitments", counts.commitments],
                  ["Pending proposals", counts.proposals_pending],
                  ["Open escalations", counts.escalations_open],
                  ["Disputes", counts.disputes_open],
                ] as const
              ).map(([label, value]) =>
                value > 0 ? (
                  <li
                    key={label}
                    className="inline-flex items-center gap-1 rounded-full bg-hover px-2 py-0.5 text-ink-600 shadow-hairline"
                  >
                    <span className="font-mono font-semibold text-ink">{value}</span>
                    {label.toLowerCase()}
                  </li>
                ) : null,
              )}
            </ul>
          ) : null}
        </header>
      ) : null}

      {/* 2 — Since you last looked (DeltaDigest — F1's future home). */}
      <DeltaDigest changes={summary?.recent_changes ?? []} loading={summaryPending} />

      {/* 3 — Needs you: inline action queue. */}
      <NeedsYou
        engagementId={engagementId}
        counts={counts}
        proposals={matrixProposals}
        nodes={allMatrixNodes}
        proposalsLoading={!data && !err}
        onChanged={() => void Promise.all([refresh(), refreshSummary()])}
      />

      {/* 4 — Narrative cards. */}
      <section aria-labelledby="brief-narrative-heading" className="space-y-2">
        <h2 id="brief-narrative-heading" className="sr-only">
          Deal narrative
        </h2>
        {!data && !err ? (
          <div className="grid gap-3 sm:grid-cols-2" data-testid="brief-narrative-shimmer">
            <ShimmerLines lines={3} />
            <ShimmerLines lines={3} />
          </div>
        ) : (
          <div className="grid gap-3 sm:grid-cols-2">
            <NarrativeCard
              title="People"
              testId="brief-card-people"
              emptyText="No stakeholders mapped yet. They appear here as interactions are imported and extraction proposals are accepted."
              items={stakeholderNodes.map((n) => ({
                id: n.id,
                label: n.title,
                meta: n.status ?? null,
              }))}
            />
            <NarrativeCard
              title="Decisions"
              testId="brief-card-decisions"
              emptyText="No decisions recorded. Accepted decisions land here with their evidence."
              items={allMatrixNodes
                .filter((n) => n.node_type === "decision")
                .map((n) => ({ id: n.id, label: n.title, meta: n.status ?? null }))}
            />
            <NarrativeCard
              title="Risks"
              testId="brief-card-risks"
              emptyText="No risks on the radar. Risks extracted from emails and meetings show up here."
              items={allMatrixNodes
                .filter((n) => n.node_type === "risk")
                .map((n) => ({ id: n.id, label: n.title, meta: n.status ?? null }))}
            />
            <NarrativeCard
              title="Commitments"
              testId="brief-card-commitments"
              emptyText="No commitments tracked yet. Promises with owners and due dates arrive with commitment tracking (Wave 3)."
              items={allMatrixNodes
                .filter((n) => n.node_type === "commitment")
                .map((n) => ({ id: n.id, label: n.title, meta: n.status ?? null }))}
            />
          </div>
        )}
      </section>

      <EngagementInsights engagementId={engagementId} />

      <RecommendationsPanel engagementId={engagementId} />

      {/* 5 — Tabs: heavy surfaces. */}
      <Tabs defaultValue="graph" className="w-full">
        <TabsList aria-label="Engagement surfaces">
          <TabsTrigger value="graph">Graph</TabsTrigger>
          <TabsTrigger value="timeline">Timeline</TabsTrigger>
          <TabsTrigger value="chat">Chat</TabsTrigger>
          <TabsTrigger value="people">People</TabsTrigger>
          <TabsTrigger value="capture">Capture</TabsTrigger>
        </TabsList>

        <TabsContent value="graph" className="space-y-2 pt-2">
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
          {!data && !err ? <ShimmerLines lines={4} /> : null}
          {data ? (
            <>
              {matrixView === "graph" ? (
                <MatrixGraph
                  nodes={matrixNodes}
                  edges={matrixEdges}
                  customTypes={data.matrix?.node_types ?? []}
                  onNodeClick={openCitation}
                  onStakeholderClick={handleStakeholderClick}
                />
              ) : matrixNodes.length === 0 ? (
                roleLens !== "all" && allMatrixNodes.length > 0 ? (
                  <p className="text-ink-600 text-sm">
                    No matrix entities visible for the {ROLE_LABEL[roleLens] ?? roleLens} lens —
                    switch to All or pick a different role.
                  </p>
                ) : (
                  <p className="text-ink-600 text-sm">
                    No matrix entities yet — add the first one below, or import an interaction in
                    the Capture tab and let extraction populate the map.
                  </p>
                )
              ) : (
                <div className="space-y-3">
                  {MATRIX_NODE_TYPES.map((t) => {
                    const nodes = matrixNodes.filter((n) => n.node_type === t);
                    if (nodes.length === 0) {
                      return null;
                    }
                    const renderList = (items: MatrixNode[]) => (
                      <ul className="border-border divide-border divide-y rounded-lg border text-sm">
                        {items.length === 0 ? (
                          <li className="text-ink-500 px-3 py-2 text-xs">
                            No {NODE_TYPE_LABEL[t]?.toLowerCase() ?? t} in the selected range.
                          </li>
                        ) : (
                          items.map((n) => {
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
                          })
                        )}
                      </ul>
                    );
                    const sectionName = NODE_TYPE_SECTION[t];
                    if (sectionName) {
                      return (
                        <SectionWithTimeline<MatrixNode>
                          key={t}
                          name={sectionName}
                          title={NODE_TYPE_LABEL[t] ?? t}
                          events={nodes}
                          getTimestamp={getNodeTimestamp}
                          headingLevel="h3"
                        >
                          {(filtered) => renderList(filtered)}
                        </SectionWithTimeline>
                      );
                    }
                    return (
                      <div key={t} className="space-y-1">
                        <h3 className="text-ink-700 text-xs font-semibold uppercase">
                          {NODE_TYPE_LABEL[t]}
                        </h3>
                        {renderList(nodes)}
                      </div>
                    );
                  })}
                </div>
              )}
              <MatrixCapture
                engagementId={engagementId}
                nodes={allMatrixNodes}
                onChanged={refresh}
              />
              <MatrixNodeDetail
                engagementId={engagementId}
                nodeId={citation.nodeId}
                title={citation.title}
                evidenceEventIds={citation.ids}
                open={citation.open}
                onClose={closeCitation}
                node={
                  citation.nodeId
                    ? (allMatrixNodes.find((n) => n.id === citation.nodeId) ?? null)
                    : null
                }
                onNodeSaved={() => {
                  void refresh();
                }}
              />
            </>
          ) : null}
        </TabsContent>

        <TabsContent value="timeline" className="space-y-3 pt-2">
          <div className="flex justify-end">
            <Link
              href={`/engagements/${encodeURIComponent(engagementId)}/timeline`}
              className="text-primary text-sm underline-offset-4 hover:underline"
            >
              Open full timeline
            </Link>
          </div>
          <EngagementTimeline engagementId={engagementId} />
        </TabsContent>

        <TabsContent value="chat" className="space-y-2 pt-2">
          <h2 className="text-ink-800 text-sm font-semibold">Chat history</h2>
          <p className="text-ink-600 text-sm">
            Your conversation with Agent Kenny on this engagement. Ask a new question from the bar
            below — every answer is grounded in ledger events.
          </p>
          <OracleChat engagementId={engagementId} variant="embedded" />
        </TabsContent>

        <TabsContent value="people" className="space-y-2 pt-2">
          <h2 className="text-ink-800 text-sm font-semibold">Team</h2>
          {!data && !err ? <ShimmerLines lines={3} /> : null}
          {data ? (
            <>
              {membersForDisplay.length === 0 ? (
                <p className="text-ink-600 text-sm">
                  No members assigned yet. Assign a teammate below so the deal has an owner —
                  they&apos;ll show up across the Brief and the timeline by name.
                </p>
              ) : (
                <ul className="divide-y divide-line rounded-card bg-surface text-sm shadow-card">
                  {membersForDisplay.map((m) => {
                    const name = displayNameForPerson(m);
                    return (
                      <li
                        key={m.id}
                        className="flex items-center justify-between gap-3 px-3 py-2 transition-colors hover:bg-hover"
                      >
                        <span className="inline-flex items-center gap-2.5 text-sm text-ink">
                          <span
                            aria-hidden="true"
                            className="flex size-6 shrink-0 items-center justify-center rounded-full bg-hover-2 text-[10px] font-semibold text-ink-600 shadow-hairline"
                          >
                            {initialsFor(name)}
                          </span>
                          <span className="min-w-0">
                            <span className="block truncate font-medium">{name}</span>
                            {m.email && m.email !== name ? (
                              <span className="text-ink-500 block truncate text-xs">{m.email}</span>
                            ) : null}
                          </span>
                        </span>
                        <div className="flex items-center gap-3">
                          <span className="inline-flex rounded-full bg-hover px-2 py-0.5 text-xs text-ink-600 shadow-hairline">
                            {memberRoleOptions.find((o) => o.name === m.role)?.label ??
                              ROLE_LABEL[m.role] ??
                              m.role}
                          </span>
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
                    );
                  })}
                </ul>
              )}
              <div className="space-y-2 rounded-card bg-surface p-3 shadow-card">
                <h3 className="text-ink-800 text-xs font-semibold">Assign a member</h3>
                <div className="flex flex-wrap items-end gap-2">
                  <div className="grid gap-1">
                    <label className="text-ink-600 text-xs" htmlFor="member-email">
                      Email
                    </label>
                    <input
                      id="member-email"
                      type="email"
                      className="rounded-control border border-transparent bg-field px-2 py-1 text-sm shadow-inset-field outline-none focus-visible:ring-2 focus-visible:ring-ring/50"
                      placeholder="user@company.com"
                      value={newEmail}
                      onChange={(e) => setNewEmail(e.target.value)}
                    />
                  </div>
                  <div className="grid gap-1">
                    <label className="text-ink-600 text-xs" htmlFor="member-role">
                      Role
                    </label>
                    <select
                      id="member-role"
                      className="rounded-control border border-transparent bg-field px-2 py-1 text-sm shadow-inset-field outline-none focus-visible:ring-2 focus-visible:ring-ring/50"
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
                    disabled={busy || !newEmail.trim()}
                    onClick={() => void addMember()}
                  >
                    Assign
                  </Button>
                </div>
              </div>
            </>
          ) : null}
        </TabsContent>

        <TabsContent value="capture" className="space-y-2 pt-2">
          <h2 className="text-ink-800 text-sm font-semibold">Interactions</h2>
          <p className="text-ink-600 text-sm">
            Drop an email, a meeting summary, a field note — or anything else that happened on this
            deployment. Each import is captured as a canonical event; the matrix grows from it via
            extraction.
          </p>
          <InteractionImport engagementId={engagementId} onChanged={refresh} />
        </TabsContent>
      </Tabs>

      {/* U4 — Kenny's front door: persistent ask-bar replaces the old
          collapsed side rail; submit opens the full-width chat overlay. */}
      <AskKennyBar
        engagementId={engagementId}
        nodes={allMatrixNodes}
        changes={summary?.recent_changes ?? []}
      />
    </div>
  );
}

function NarrativeCard({
  title,
  items,
  emptyText,
  testId,
}: {
  title: string;
  items: Array<{ id: string; label: string; meta: string | null }>;
  emptyText: string;
  testId: string;
}) {
  return (
    <section
      aria-label={title}
      data-testid={testId}
      className="space-y-1.5 rounded-card bg-surface p-3 shadow-card"
    >
      <h3 className="text-ink-800 text-sm font-semibold">{title}</h3>
      {items.length === 0 ? (
        <p className="text-ink-600 text-xs">{emptyText}</p>
      ) : (
        <ul className="space-y-1 text-sm">
          {items.slice(0, 8).map((item) => (
            <li key={item.id} className="flex items-center justify-between gap-3">
              <span className="text-ink-800 truncate">{item.label}</span>
              {item.meta ? <span className="text-ink-500 shrink-0 text-xs">{item.meta}</span> : null}
            </li>
          ))}
          {items.length > 8 ? (
            <li className="text-ink-500 text-xs">+ {items.length - 8} more in the Graph tab</li>
          ) : null}
        </ul>
      )}
    </section>
  );
}
