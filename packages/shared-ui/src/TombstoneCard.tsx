"use client";

import * as React from "react";
import { Archive, Shield } from "lucide-react";

import { cn } from "./lib/utils";

export type TombstoneCardProps = {
  /** Plain-language why this node was removed (retention, policy, etc.). */
  retentionReason: string;
  /** Display string for `destroyed_at` (RFC 3339 / user-localized in host). */
  destroyedAt: string;
  originalNodeId: string;
  authorityActor: string;
  /** Whether RFC 3161 / audit timestamp verification passed (Story 1.8). */
  rfc3161Verified?: boolean;
  /** If true, show optional appeal CTA. */
  appealAvailable?: boolean;
  onAppeal?: () => void;
  className?: string;
  id?: string;
};

/**
 * Human-readable tombstone for removed memory nodes (UX-DR11, FR5). Reached from
 * `CitationChip` tombstoned state or evidence routes. Optional appeal is audit/reviewer
 * (Epic 10+), not a legal guarantee of restore.
 */
export function TombstoneCard({
  retentionReason,
  destroyedAt,
  originalNodeId,
  authorityActor,
  rfc3161Verified = true,
  appealAvailable = false,
  onAppeal,
  className: classNameProp,
  id: idProp,
}: TombstoneCardProps) {
  const baseId = idProp ?? React.useId();
  const titleId = `${baseId}-title`;

  return (
    <article
      data-testid="tombstone-card"
      aria-labelledby={titleId}
      className={cn(
        "max-w-[min(100%,40rem)] rounded-lg border border-border bg-paper-200/80 p-4 text-ink-900",
        classNameProp,
      )}
    >
      <div className="flex items-start gap-2">
        <Archive className="mt-0.5 size-5 shrink-0 text-ink-600" aria-hidden />
        <div className="min-w-0">
          <h2 id={titleId} className="text-base font-semibold text-ink-900">
            Content no longer in memory
          </h2>
          <p className="mt-1 text-sm text-ink-800">{retentionReason}</p>
        </div>
      </div>
      <dl className="mt-4 space-y-2 text-sm text-ink-800">
        <div className="flex flex-col gap-0.5 sm:flex-row sm:gap-2">
          <dt className="shrink-0 font-medium text-ink-900">Removed at</dt>
          <dd>{destroyedAt}</dd>
        </div>
        <div className="flex flex-col gap-0.5 sm:flex-row sm:gap-2">
          <dt className="shrink-0 font-medium text-ink-900">Original node</dt>
          <dd className="min-w-0 break-all font-mono text-xs">{originalNodeId}</dd>
        </div>
        <div className="flex flex-col gap-0.5 sm:flex-row sm:gap-2">
          <dt className="shrink-0 font-medium text-ink-900">Authorized by</dt>
          <dd>{authorityActor}</dd>
        </div>
      </dl>
      <p className="mt-3 flex items-center gap-1.5 text-xs text-ink-600">
        <Shield className="size-3.5" aria-hidden />
        <span>
          Timestamp {rfc3161Verified ? "verified (RFC 3161 trail)" : "not verified"} in audit log
        </span>
      </p>
      {appealAvailable && onAppeal ? (
        <div className="mt-4 border-t border-border pt-3">
          <button
            type="button"
            className="inline-flex h-9 min-w-11 items-center justify-center rounded-md border border-border bg-paper-100 px-3 text-sm font-medium text-ink-900 hover:bg-paper-200 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
            onClick={onAppeal}
          >
            Request review
          </button>
        </div>
      ) : null}
    </article>
  );
}
