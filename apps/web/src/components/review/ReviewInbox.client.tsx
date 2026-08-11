"use client";

import * as React from "react";
import { toast } from "sonner";

import { TimestampLabel } from "@/components/common/TimestampLabel.client";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import type { Engagement } from "@/lib/bff/engagement-types";
import type { MatrixProposal } from "@/lib/bff/matrix-types";
import { readStrategistBffErrorDescription } from "@/lib/bff/read-strategist-bff-error";
import type { ReviewInboxKind, ReviewItem, ReviewItemStatus } from "@/lib/bff/review-types";

/**
 * Pilot-refresh E1 — the unified Review Inbox. One queue surface over four
 * item kinds:
 *
 * - extraction proposals — existing `matrix_proposals` storage, listed via
 *   the engagement detail aggregate when an engagement filter is set;
 * - agent escalations (E2) — resolving with an answer records the canonical
 *   `human_escalation_answer` ledger event (knowledge flywheel);
 * - citation disputes (E3) — resolved with a note;
 * - commitment confirmations — schema slot now, feature arrives Wave 3.
 */

const KIND_TABS: ReadonlyArray<{ key: "all" | ReviewInboxKind; label: string }> = [
  { key: "all", label: "All" },
  { key: "agent_escalation", label: "Escalations" },
  { key: "citation_dispute", label: "Citation disputes" },
  { key: "extraction_proposal", label: "Extraction proposals" },
  { key: "commitment_confirmation", label: "Commitments" },
];

const STATUSES: ReadonlyArray<ReviewItemStatus> = ["open", "resolved", "dismissed"];

export function ReviewInbox() {
  const [items, setItems] = React.useState<ReviewItem[]>([]);
  const [proposals, setProposals] = React.useState<MatrixProposal[]>([]);
  const [engagements, setEngagements] = React.useState<Engagement[]>([]);
  const [kindTab, setKindTab] = React.useState<"all" | ReviewInboxKind>("all");
  const [status, setStatus] = React.useState<ReviewItemStatus>("open");
  const [engagementId, setEngagementId] = React.useState<string>("");
  const [loading, setLoading] = React.useState(true);
  const [err, setErr] = React.useState<string | null>(null);
  const [busyId, setBusyId] = React.useState<string | null>(null);

  const showProposals =
    (kindTab === "all" || kindTab === "extraction_proposal") && engagementId !== "";
  const storedKind = kindTab === "all" || kindTab === "extraction_proposal" ? null : kindTab;

  const fetchItems = React.useCallback(async () => {
    if (kindTab === "extraction_proposal") {
      setItems([]);
      return;
    }
    const params = new URLSearchParams({ status });
    if (storedKind) params.set("kind", storedKind);
    if (engagementId) params.set("engagementId", engagementId);
    const r = await fetch(`/api/bff/review/items?${params.toString()}`, { cache: "no-store" });
    if (!r.ok) {
      setErr(await readStrategistBffErrorDescription(r));
      return;
    }
    setErr(null);
    const body = (await r.json()) as { items?: ReviewItem[] };
    setItems(Array.isArray(body.items) ? body.items : []);
  }, [kindTab, storedKind, status, engagementId]);

  const fetchProposals = React.useCallback(async () => {
    if (!showProposals) {
      setProposals([]);
      return;
    }
    const r = await fetch(`/api/bff/engagements/${encodeURIComponent(engagementId)}`, {
      cache: "no-store",
    });
    if (!r.ok) {
      // Non-fatal: the review_items half of the inbox still renders.
      setProposals([]);
      return;
    }
    const body = (await r.json()) as { matrix?: { proposals?: MatrixProposal[] } };
    const all = Array.isArray(body.matrix?.proposals) ? body.matrix.proposals : [];
    const wanted = status === "open" ? "pending" : status === "resolved" ? "accepted" : "rejected";
    setProposals(all.filter((p) => p.status === wanted));
  }, [showProposals, engagementId, status]);

  React.useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const r = await fetch("/api/bff/engagements", { cache: "no-store" });
        if (!cancelled && r.ok) {
          const body = (await r.json()) as { engagements?: Engagement[] };
          setEngagements(Array.isArray(body.engagements) ? body.engagements : []);
        }
      } catch {
        // Engagement filter degrades to "all engagements".
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  React.useEffect(() => {
    let cancelled = false;
    void (async () => {
      setLoading(true);
      try {
        await Promise.all([fetchItems(), fetchProposals()]);
      } catch (e) {
        if (!cancelled) {
          setErr(e instanceof Error ? e.message : "Could not load the review inbox.");
        }
      }
      if (!cancelled) {
        setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [fetchItems, fetchProposals]);

  const decideItem = React.useCallback(
    async (
      item: ReviewItem,
      decision: "resolve" | "dismiss",
      body: Record<string, unknown>,
    ): Promise<boolean> => {
      setBusyId(item.id);
      // Optimistic: drop the card immediately; restore on failure.
      const before = items;
      setItems((prev) => prev.filter((i) => i.id !== item.id));
      try {
        const r = await fetch(`/api/bff/review/items/${encodeURIComponent(item.id)}/${decision}`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        });
        if (!r.ok) {
          setItems(before);
          toast.error(
            decision === "resolve" ? "Could not resolve item" : "Could not dismiss item",
            { description: (await readStrategistBffErrorDescription(r)).slice(0, 240) },
          );
          return false;
        }
        toast.success(decision === "resolve" ? "Resolved" : "Dismissed");
        return true;
      } finally {
        setBusyId(null);
      }
    },
    [items],
  );

  const decideProposal = React.useCallback(
    async (proposal: MatrixProposal, decision: "accept" | "reject") => {
      setBusyId(proposal.id);
      const before = proposals;
      setProposals((prev) => prev.filter((p) => p.id !== proposal.id));
      try {
        const r = await fetch(
          `/api/bff/engagements/${encodeURIComponent(proposal.engagement_id)}/proposals/` +
            `${encodeURIComponent(proposal.id)}/${decision}`,
          { method: "POST" },
        );
        if (!r.ok) {
          setProposals(before);
          toast.error(
            decision === "accept" ? "Could not accept proposal" : "Could not reject proposal",
            { description: (await readStrategistBffErrorDescription(r)).slice(0, 240) },
          );
          return;
        }
        toast.success(decision === "accept" ? "Proposal accepted" : "Proposal rejected");
      } finally {
        setBusyId(null);
      }
    },
    [proposals],
  );

  const visibleItems = React.useMemo(
    () => (kindTab === "all" ? items : items.filter((i) => i.kind === kindTab)),
    [items, kindTab],
  );

  const empty = !loading && visibleItems.length === 0 && (!showProposals || proposals.length === 0);

  return (
    <section aria-labelledby="review-inbox-heading" className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 id="review-inbox-heading" className="text-xl font-semibold">
            Review inbox
          </h1>
          <p className="text-ink-600 mt-1 text-sm">
            Everything the agents want a human to look at — proposals, escalations, and disputed
            citations. Every decision lands in the audit ledger.
          </p>
        </div>
      </div>

      <div className="flex flex-wrap items-end gap-3" role="group" aria-label="Filter review items">
        <div className="flex flex-wrap gap-1" role="tablist" aria-label="Item kind">
          {KIND_TABS.map((tab) => (
            <Button
              key={tab.key}
              type="button"
              variant="ghost"
              size="sm"
              role="tab"
              aria-selected={kindTab === tab.key}
              onClick={() => setKindTab(tab.key)}
              className={
                "h-auto rounded-control px-2.5 py-1 text-sm transition-colors " +
                (kindTab === tab.key
                  ? "bg-surface font-medium text-ink shadow-btn hover:bg-surface"
                  : "text-ink-600 hover:bg-hover hover:text-ink")
              }
            >
              {tab.label}
            </Button>
          ))}
        </div>
        <div className="grid gap-1">
          <label className="text-ink-600 text-xs" htmlFor="review-filter-status">
            Status
          </label>
          <select
            id="review-filter-status"
            className="rounded-control border border-transparent bg-field px-2 py-1 text-sm shadow-inset-field outline-none focus-visible:ring-2 focus-visible:ring-ring/50"
            value={status}
            onChange={(e) => setStatus(e.target.value as ReviewItemStatus)}
          >
            {STATUSES.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
        </div>
        <div className="grid gap-1">
          <label className="text-ink-600 text-xs" htmlFor="review-filter-engagement">
            Engagement
          </label>
          <select
            id="review-filter-engagement"
            className="rounded-control border border-transparent bg-field px-2 py-1 text-sm shadow-inset-field outline-none focus-visible:ring-2 focus-visible:ring-ring/50"
            value={engagementId}
            onChange={(e) => setEngagementId(e.target.value)}
          >
            <option value="">All engagements</option>
            {engagements.map((e) => (
              <option key={e.id} value={e.id}>
                {e.name}
              </option>
            ))}
          </select>
        </div>
      </div>

      {err ? <p className="text-red-ink text-sm">{err}</p> : null}
      {loading ? <p className="text-ink-600 text-sm">Loading…</p> : null}

      {kindTab === "commitment_confirmation" && !loading && visibleItems.length === 0 ? (
        <p className="text-ink-600 text-sm">
          No commitment confirmations yet — commitment tracking ships in Wave 3; extracted promises
          below the auto-accept threshold will queue here for confirmation.
        </p>
      ) : null}

      {(kindTab === "all" || kindTab === "extraction_proposal") &&
      engagementId === "" &&
      !loading ? (
        <p className="text-ink-600 text-sm">
          Select an engagement to include its pending extraction proposals in the queue.
        </p>
      ) : null}

      {showProposals && proposals.length > 0 ? (
        <ul className="space-y-2" aria-label="Extraction proposals">
          {proposals.map((p) => (
            <ProposalCard
              key={p.id}
              proposal={p}
              busy={busyId === p.id}
              onDecide={decideProposal}
            />
          ))}
        </ul>
      ) : null}

      {visibleItems.length > 0 ? (
        <ul className="space-y-2" aria-label="Review items">
          {visibleItems.map((item) => (
            <ReviewItemCard
              key={item.id}
              item={item}
              busy={busyId === item.id}
              onDecide={decideItem}
            />
          ))}
        </ul>
      ) : null}

      {empty && kindTab !== "commitment_confirmation" ? (
        <p className="text-ink-600 text-sm">
          Nothing waiting for review — escalations, disputes, and proposals will land here as the
          agents work.
        </p>
      ) : null}
    </section>
  );
}

function KindBadge({ kind }: { kind: string }) {
  return (
    <span className="rounded-full bg-hover px-1.5 py-0.5 font-mono text-[10px] uppercase text-ink-600 shadow-hairline">
      {kind.replace(/_/g, " ")}
    </span>
  );
}

function ProposalCard({
  proposal,
  busy,
  onDecide,
}: {
  proposal: MatrixProposal;
  busy: boolean;
  onDecide: (proposal: MatrixProposal, decision: "accept" | "reject") => void;
}) {
  const payload = (proposal.payload ?? {}) as Record<string, unknown>;
  const title =
    proposal.proposal_kind === "node"
      ? `${typeof payload.node_type === "string" ? payload.node_type : "node"}: ${
          typeof payload.title === "string" ? payload.title : "(no title)"
        }`
      : `edge: ${typeof payload.edge_type === "string" ? payload.edge_type : "(unknown)"}`;
  const sampled = payload.sampling_audit === true;
  return (
    <li className="space-y-1 rounded-card bg-surface px-3 py-2.5 shadow-card">
      <div className="flex items-center justify-between gap-3">
        <div className="flex min-w-0 items-center gap-2">
          <KindBadge kind="extraction_proposal" />
          {sampled ? (
            <span className="rounded-full bg-orange-tint px-1.5 py-0.5 font-mono text-[10px] uppercase text-orange-ink shadow-hairline">
              audit sample
            </span>
          ) : null}
          <span className="truncate text-sm font-medium text-ink">{title}</span>
        </div>
        {proposal.status === "pending" ? (
          <div className="flex gap-1">
            <Button
              type="button"
              size="sm"
              className="h-7 px-2 text-xs"
              disabled={busy}
              onClick={() => onDecide(proposal, "accept")}
            >
              Accept
            </Button>
            <Button
              type="button"
              size="sm"
              variant="outline"
              className="h-7 px-2 text-xs"
              disabled={busy}
              onClick={() => onDecide(proposal, "reject")}
            >
              Reject
            </Button>
          </div>
        ) : null}
      </div>
      {proposal.rationale ? <p className="text-ink-600 text-xs">{proposal.rationale}</p> : null}
      <TimestampLabel value={proposal.created_at} prefix="proposed" />
    </li>
  );
}

function ReviewItemCard({
  item,
  busy,
  onDecide,
}: {
  item: ReviewItem;
  busy: boolean;
  onDecide: (
    item: ReviewItem,
    decision: "resolve" | "dismiss",
    body: Record<string, unknown>,
  ) => Promise<boolean>;
}) {
  const [answering, setAnswering] = React.useState(false);
  const [answerText, setAnswerText] = React.useState("");
  const [answerCitations, setAnswerCitations] = React.useState("");
  const [note, setNote] = React.useState("");
  const payload = item.payload ?? {};

  const submitAnswer = async () => {
    if (!answerText.trim()) {
      toast.error("An answer is required to resolve an escalation");
      return;
    }
    const citations = answerCitations
      .split(/[\s,]+/)
      .map((c) => c.trim())
      .filter(Boolean);
    const ok = await onDecide(item, "resolve", {
      resolution_note: note.trim() || null,
      answer_text: answerText.trim(),
      answer_citations: citations,
    });
    if (ok) {
      setAnswering(false);
    }
  };

  return (
    <li className="space-y-2 rounded-card bg-surface px-3 py-2.5 shadow-card">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 space-y-1">
          <div className="flex flex-wrap items-center gap-2">
            <KindBadge kind={item.kind} />
            <StatusBadge status={item.status} />
            <TimestampLabel value={item.created_at} prefix="filed" />
            {item.created_by ? (
              <span className="text-ink-500 font-mono text-[10px]">by {item.created_by}</span>
            ) : null}
          </div>
          {item.kind === "agent_escalation" ? (
            <>
              <p className="text-sm font-medium text-ink">{String(payload.question ?? "")}</p>
              <p className="text-ink-600 text-xs">
                Declined because: {String(payload.reason ?? "(no reason recorded)")}
              </p>
              {typeof payload.answer_text === "string" && payload.answer_text ? (
                <p className="text-ink-600 text-xs">Answer: {payload.answer_text}</p>
              ) : null}
            </>
          ) : item.kind === "citation_dispute" ? (
            <>
              <p className="text-sm font-medium text-ink">
                Disputed citation{" "}
                <span className="font-mono text-xs">{String(payload.citation_id ?? "")}</span>
              </p>
              <p className="text-ink-600 text-xs">{String(payload.reason ?? "")}</p>
            </>
          ) : (
            <p className="text-sm font-medium text-ink">Commitment confirmation</p>
          )}
          {item.resolution_note ? (
            <p className="text-ink-500 text-xs">Note: {item.resolution_note}</p>
          ) : null}
        </div>
        {item.status === "open" ? (
          <div className="flex shrink-0 gap-1">
            {item.kind === "agent_escalation" ? (
              <Button
                type="button"
                size="sm"
                className="h-7 px-2 text-xs"
                disabled={busy}
                onClick={() => setAnswering((v) => !v)}
                aria-expanded={answering}
              >
                Answer
              </Button>
            ) : (
              <Button
                type="button"
                size="sm"
                className="h-7 px-2 text-xs"
                disabled={busy}
                onClick={() =>
                  void onDecide(item, "resolve", { resolution_note: note.trim() || null })
                }
              >
                Resolve
              </Button>
            )}
            <Button
              type="button"
              size="sm"
              variant="ghost"
              className="h-7 px-2 text-xs"
              disabled={busy}
              onClick={() =>
                void onDecide(item, "dismiss", { resolution_note: note.trim() || null })
              }
            >
              Dismiss
            </Button>
          </div>
        ) : null}
      </div>

      {answering && item.status === "open" ? (
        <div className="space-y-2 rounded-md bg-inset p-2 shadow-hairline">
          <div className="space-y-1">
            <Label htmlFor={`answer-${item.id}`} className="text-xs">
              Answer (recorded as canonical knowledge with citations)
            </Label>
            <Textarea
              id={`answer-${item.id}`}
              value={answerText}
              onChange={(e) => setAnswerText(e.target.value)}
              placeholder="What the agent should have answered…"
              rows={3}
            />
          </div>
          <div className="space-y-1">
            <Label htmlFor={`citations-${item.id}`} className="text-xs">
              Citations (event ids, comma or space separated — optional)
            </Label>
            <Input
              id={`citations-${item.id}`}
              value={answerCitations}
              onChange={(e) => setAnswerCitations(e.target.value)}
              placeholder="event-id, event-id"
              autoComplete="off"
            />
          </div>
          <div className="space-y-1">
            <Label htmlFor={`note-${item.id}`} className="text-xs">
              Resolution note (optional)
            </Label>
            <Input
              id={`note-${item.id}`}
              value={note}
              onChange={(e) => setNote(e.target.value)}
              autoComplete="off"
            />
          </div>
          <div className="flex gap-2">
            <Button
              type="button"
              size="sm"
              className="h-7 px-2 text-xs"
              disabled={busy}
              onClick={() => void submitAnswer()}
            >
              Submit answer
            </Button>
            <Button
              type="button"
              size="sm"
              variant="ghost"
              className="h-7 px-2 text-xs"
              onClick={() => setAnswering(false)}
            >
              Cancel
            </Button>
          </div>
        </div>
      ) : null}
    </li>
  );
}

function StatusBadge({ status }: { status: ReviewItem["status"] }) {
  const classes =
    status === "open"
      ? "bg-accent-tint text-accent-ink"
      : status === "resolved"
        ? "bg-hover text-ink-600"
        : "bg-hover text-ink-500";
  return (
    <span
      className={`rounded-full px-1.5 py-0.5 font-mono text-[10px] uppercase shadow-hairline ${classes}`}
      aria-label={`status ${status}`}
    >
      {status}
    </span>
  );
}
