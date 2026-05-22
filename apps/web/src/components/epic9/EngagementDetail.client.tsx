"use client";

import Link from "next/link";
import * as React from "react";
import { toast } from "sonner";

import { MatrixCapture } from "@/components/epic9/MatrixCapture.client";
import { Button } from "@/components/ui/button";
import type { EngagementLogEntry } from "@/lib/bff/engagement-log-types";
import type { Engagement, EngagementMember } from "@/lib/bff/engagement-types";
import type { MatrixEdge, MatrixNode } from "@/lib/bff/matrix-types";
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

const ROLE_SHORT: Record<string, string> = {
  fde: "FDE",
  deployment_strategist: "Strategist",
  biz_dev: "Biz dev",
};

const MEMBER_ROLES = ["fde", "deployment_strategist", "biz_dev"] as const;
const LOG_KINDS = ["meeting", "decision", "risk", "next_action"] as const;

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
  log: EngagementLogEntry[];
  matrix?: { nodes: MatrixNode[]; edges: MatrixEdge[] };
};

/**
 * Engagement detail — one customer deployment: its team, the deployment
 * matrix (typed nodes + edges), a cross-role activity breakdown, and the
 * role-lens-filterable log.
 */
export function EngagementDetail({ engagementId }: { engagementId: string }) {
  const [data, setData] = React.useState<DetailResponse | null>(null);
  const [err, setErr] = React.useState<string | null>(null);
  const [newUserId, setNewUserId] = React.useState("");
  const [newRole, setNewRole] = React.useState<string>("fde");
  const [roleLens, setRoleLens] = React.useState<string>("all");
  const [busy, setBusy] = React.useState(false);

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

  const log = data?.log ?? [];
  const lensedLog = roleLens === "all" ? log : log.filter((e) => e.author_role === roleLens);
  const breakdown = MEMBER_ROLES.map((role) => {
    const counts = LOG_KINDS.map(
      (kind) => log.filter((e) => e.author_role === role && e.entry_kind === kind).length,
    );
    return { role, counts, total: counts.reduce((a, b) => a + b, 0) };
  });
  const gapRoles = breakdown.filter((b) => b.total === 0).map((b) => b.role);
  const unattributedCount = log.filter(
    (e) => !MEMBER_ROLES.some((r) => r === e.author_role),
  ).length;

  const matrixNodes = data?.matrix?.nodes ?? [];
  const matrixEdges = data?.matrix?.edges ?? [];
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
                      <span className="text-ink-700">{ROLE_LABEL[m.role] ?? m.role}</span>
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
                    {MEMBER_ROLES.map((r) => (
                      <option key={r} value={r}>
                        {ROLE_LABEL[r]}
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

          <section className="space-y-2">
            <h2 className="text-ink-800 text-sm font-semibold">Deployment matrix</h2>
            {matrixNodes.length === 0 ? (
              <p className="text-ink-600 text-sm">
                No matrix entities yet — add the first one below, or let ingestion (Phase 6)
                populate the map.
              </p>
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
            <MatrixCapture engagementId={engagementId} nodes={matrixNodes} onChanged={refresh} />
          </section>

          {log.length > 0 ? (
            <section className="space-y-2">
              <h2 className="text-ink-800 text-sm font-semibold">Cross-role view</h2>
              <p className="text-ink-600 text-sm">
                Log entries per team role — a count of who is recording what. A row of zeros is a
                role that has not weighed in.
              </p>
              <div className="border-border overflow-x-auto rounded-lg border">
                <table className="w-full text-left text-sm">
                  <thead className="bg-paper-200/80 text-ink-700">
                    <tr>
                      <th className="px-3 py-2 font-medium">Role</th>
                      {LOG_KINDS.map((k) => (
                        <th key={k} className="px-3 py-2 font-medium capitalize">
                          {k.replace("_", " ")}
                        </th>
                      ))}
                      <th className="px-3 py-2 font-medium">Total</th>
                    </tr>
                  </thead>
                  <tbody>
                    {breakdown.map((row) => (
                      <tr key={row.role} className="border-border border-t">
                        <td className="px-3 py-2 font-medium">{ROLE_SHORT[row.role]}</td>
                        {row.counts.map((n, i) => (
                          <td
                            key={LOG_KINDS[i]}
                            className={
                              n === 0 ? "text-ink-400 px-3 py-2" : "text-ink-700 px-3 py-2"
                            }
                          >
                            {n}
                          </td>
                        ))}
                        <td className="text-ink-800 px-3 py-2 font-medium">{row.total}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {gapRoles.length > 0 ? (
                <p className="text-ink-600 text-sm">
                  No log activity yet from: {gapRoles.map((r) => ROLE_LABEL[r]).join(", ")}.
                </p>
              ) : null}
              {unattributedCount > 0 ? (
                <p className="text-ink-500 text-xs">
                  Excludes {unattributedCount} {unattributedCount === 1 ? "entry" : "entries"}{" "}
                  logged before role attribution.
                </p>
              ) : null}
            </section>
          ) : null}

          <section className="space-y-2">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <h2 className="text-ink-800 text-sm font-semibold">Log</h2>
              {log.length > 0 ? (
                <div className="flex items-center gap-2">
                  <label className="text-ink-600 text-xs" htmlFor="role-lens">
                    Role lens
                  </label>
                  <select
                    id="role-lens"
                    className="border-border rounded-md border px-2 py-1 text-sm"
                    value={roleLens}
                    onChange={(e) => setRoleLens(e.target.value)}
                  >
                    <option value="all">All roles</option>
                    {MEMBER_ROLES.map((r) => (
                      <option key={r} value={r}>
                        {ROLE_LABEL[r]}
                      </option>
                    ))}
                  </select>
                </div>
              ) : null}
            </div>
            {log.length === 0 ? (
              <p className="text-ink-600 text-sm">
                No log entries yet — capture meetings, decisions, risks, and next actions from the
                action queue.
              </p>
            ) : lensedLog.length === 0 ? (
              <p className="text-ink-600 text-sm">
                No entries from {ROLE_LABEL[roleLens] ?? roleLens} on this engagement.
              </p>
            ) : (
              <ul className="border-border divide-border divide-y rounded-lg border text-sm">
                {lensedLog.map((e) => (
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
                    {e.author_role || e.author ? (
                      <p className="text-ink-500 text-xs">
                        — {e.author_role ? (ROLE_LABEL[e.author_role] ?? e.author_role) : e.author}
                      </p>
                    ) : null}
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
