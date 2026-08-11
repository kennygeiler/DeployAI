"use client";

import Link from "next/link";
import * as React from "react";

import { MatrixProposals } from "@/components/epic9/MatrixProposals.client";
import type { EngagementSummaryCounts } from "@/lib/bff/summary-types";
import type { MatrixNode, MatrixProposal } from "@/lib/bff/matrix-types";

/**
 * Wave 2.5 U3 — "Needs you": the inline action queue on the Brief.
 *
 * Pending extraction proposals are actionable inline (reusing the
 * MatrixProposals accept/reject surface); escalations and disputes link
 * into the Review Inbox where their answer/resolve flows already live.
 */
export function NeedsYou({
  engagementId,
  counts,
  proposals,
  nodes,
  proposalsLoading = false,
  onChanged,
}: {
  engagementId: string;
  counts: EngagementSummaryCounts | null;
  proposals: MatrixProposal[];
  nodes: MatrixNode[];
  proposalsLoading?: boolean;
  onChanged: () => void | Promise<void>;
}) {
  const pending = React.useMemo(
    () => proposals.filter((p) => p.status === "pending"),
    [proposals],
  );
  const escalations = counts?.escalations_open ?? 0;
  const disputes = counts?.disputes_open ?? 0;
  const pendingCount = counts?.proposals_pending ?? pending.length;
  const nothingWaiting =
    !proposalsLoading && pending.length === 0 && escalations === 0 && disputes === 0;

  const reviewHref = `/review?engagementId=${encodeURIComponent(engagementId)}`;

  return (
    <section aria-labelledby="needs-you-heading" data-testid="needs-you" className="space-y-2">
      <div className="flex items-center gap-2">
        <h2 id="needs-you-heading" className="text-ink-800 text-sm font-semibold">
          Needs you
        </h2>
        {pendingCount + escalations + disputes > 0 ? (
          <span
            className="rounded-full bg-accent-tint px-1.5 py-0.5 font-mono text-[10px] font-semibold text-accent-ink shadow-hairline"
            aria-label={`${pendingCount + escalations + disputes} item(s) waiting`}
          >
            {pendingCount + escalations + disputes}
          </span>
        ) : null}
      </div>

      {escalations > 0 || disputes > 0 ? (
        <div className="flex flex-wrap gap-2 text-sm" data-testid="needs-you-review-links">
          {escalations > 0 ? (
            <Link
              href={reviewHref}
              className="rounded-card bg-surface px-3 py-2 shadow-card transition-colors hover:bg-hover"
            >
              <span className="font-medium text-ink">{escalations}</span>{" "}
              <span className="text-ink-600">
                open escalation{escalations === 1 ? "" : "s"} — answer in the Review Inbox
              </span>
            </Link>
          ) : null}
          {disputes > 0 ? (
            <Link
              href={reviewHref}
              className="rounded-card bg-surface px-3 py-2 shadow-card transition-colors hover:bg-hover"
            >
              <span className="font-medium text-ink">{disputes}</span>{" "}
              <span className="text-ink-600">
                citation dispute{disputes === 1 ? "" : "s"} to resolve
              </span>
            </Link>
          ) : null}
        </div>
      ) : null}

      {proposalsLoading ? (
        <p className="text-ink-600 text-sm">Loading proposals…</p>
      ) : pending.length > 0 ? (
        <MatrixProposals
          engagementId={engagementId}
          proposals={proposals}
          nodes={nodes}
          onChanged={onChanged}
        />
      ) : null}

      {nothingWaiting ? (
        <p className="text-ink-600 text-sm" data-testid="needs-you-empty">
          Nothing waiting on you. Extraction proposals, agent escalations, and citation disputes
          queue here the moment they need a human decision.
        </p>
      ) : null}
    </section>
  );
}
