"use client";

import { DigestEvidenceCard } from "./DigestEvidenceCard.client";
import type {
  DigestRankedOutItem,
  DigestTopItem,
} from "@/lib/strategist-data/strategist-surface-types";
import { useStrategistSurface } from "@/lib/epic8/strategist-surface-context";

export type MorningDigestClientProps = {
  topItems?: readonly DigestTopItem[];
  /**
   * Optional ranked-out lines from telemetry (e.g. control-plane pilot surface). When omitted, the
   * subsection is hidden.
   */
  rankedOutItems?: readonly DigestRankedOutItem[];
  /**
   * When false, digest rows (including empty) must not be interpreted as canonical materialized memory.
   */
  dataTrusted?: boolean;
  /** Server-computed notice when the digest feed failed validation, HTTP, or configuration. */
  digestBanner?: string | null;
};

export function MorningDigestClient({
  topItems = [],
  rankedOutItems,
  dataTrusted = true,
  digestBanner,
}: MorningDigestClientProps) {
  const { agentDegraded } = useStrategistSurface();

  return (
    <div className="flex flex-col gap-8">
      <div>
        <h1 className="text-display text-ink-950 font-semibold tracking-tight">Morning digest</h1>
        <p className="text-body text-ink-600 mt-1 max-w-2xl">
          Phase-contextual priorities for today — three items (FR34). No loading shimmer on agent
          body text (UX-DR23).
        </p>
        {!dataTrusted ? (
          <p
            className="text-ink-800 mt-2 max-w-2xl rounded-md border border-amber-600/30 bg-amber-50/80 px-3 py-2 text-sm"
            role="status"
          >
            Digest data is not trusted for this request (missing feed, control-plane error, or
            validation failure). Treat the surface as empty of canonical rows.
          </p>
        ) : null}
        {digestBanner ? (
          <p className="text-ink-800 mt-2 max-w-2xl rounded-md border border-amber-600/30 bg-amber-50/80 px-3 py-2 text-sm">
            {digestBanner}
          </p>
        ) : null}
        {agentDegraded ? (
          <p className="text-ink-800 mt-2 max-w-2xl rounded-md border border-amber-600/30 bg-amber-50/80 px-3 py-2 text-sm">
            Agent ranking is paused; evidence below shows the last materialized sync from canonical
            memory only (FR46).
          </p>
        ) : null}
      </div>
      {topItems.length === 0 ? (
        <p className="text-ink-700 mt-4 max-w-2xl text-sm" role="status">
          No digest rows for your organization yet. Connect integrations and run ingestion, or
          verify pilot digest configuration on the control plane.
        </p>
      ) : (
        <div
          className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3"
          data-testid="morning-digest-top"
        >
          {topItems.map((item) => (
            <DigestEvidenceCard key={item.id} item={item} headingLevel="h2" />
          ))}
        </div>
      )}
      {!agentDegraded && (rankedOutItems?.length ?? 0) > 0 ? (
        <footer className="border-border rounded-lg border border-dashed p-4">
          <h2 className="text-foreground text-sm font-semibold">What I ranked out</h2>
          <ul className="text-body text-ink-700 mt-2 list-inside list-disc space-y-1">
            {rankedOutItems!.map((o) => (
              <li key={o.id}>
                <span className="font-medium text-ink-900">{o.label}</span> — {o.reason}
              </li>
            ))}
          </ul>
        </footer>
      ) : null}
    </div>
  );
}
