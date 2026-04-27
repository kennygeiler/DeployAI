"use client";

import Link from "next/link";

import { DigestEvidenceCard } from "./DigestEvidenceCard.client";
import type { DigestTopItem, EveningPatternRow } from "@/lib/epic8/mock-digest";
import { EVENING_CANDIDATES, MORNING_DIGEST_TOP } from "@/lib/epic8/mock-digest";
import { useStrategistSurface } from "@/lib/epic8/strategist-surface-context";

export type EveningSynthesisClientProps = {
  initialCandidates?: readonly DigestTopItem[];
  initialPatterns?: readonly EveningPatternRow[];
  eveningBanner?: string | null;
};

/**
 * Parallel to morning digest: candidate learnings + Class B entry (FR35, Story 8.3).
 * Server may pass remote-validated rows; when omitted, uses digest slice + `EVENING_CANDIDATES`.
 */
export function EveningSynthesisClient({
  initialCandidates,
  initialPatterns,
  eveningBanner,
}: EveningSynthesisClientProps) {
  const { agentDegraded } = useStrategistSurface();
  const candidates = initialCandidates ?? MORNING_DIGEST_TOP.slice(0, 2);
  const patterns = initialPatterns ?? EVENING_CANDIDATES;
  const displayCandidates = candidates.slice(0, 2);

  return (
    <div className="flex flex-col gap-8">
      <div>
        <h1 className="text-display text-ink-950 font-semibold tracking-tight">
          Evening synthesis
        </h1>
        <p className="text-body text-ink-600 mt-1 max-w-2xl">
          End-of-day review: candidate learnings, cross-account patterns, and Class B follow-up
          (NFR3 by 19:00 local when the job is wired).
        </p>
        {eveningBanner ? (
          <p
            className="text-ink-800 mt-2 max-w-2xl rounded-md border border-amber-600/30 bg-amber-50/80 px-3 py-2 text-sm"
            role="status"
          >
            {eveningBanner}
          </p>
        ) : null}
        {agentDegraded ? (
          <p
            className="text-ink-800 mt-2 max-w-2xl rounded-md border border-amber-600/30 bg-amber-50/80 px-3 py-2 text-sm"
            role="status"
          >
            Synthesis suggestions are held; cards show last synced canonical snippets (FR46).
          </p>
        ) : null}
      </div>
      <div
        className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3"
        data-testid="evening-candidates"
      >
        {displayCandidates.map((item) => (
          <DigestEvidenceCard key={item.id} item={item} headingLevel="h2" />
        ))}
      </div>
      {!agentDegraded ? (
        <section className="border-border rounded-lg border p-4" aria-labelledby="evening-patterns">
          <h2 id="evening-patterns" className="text-foreground text-sm font-semibold">
            Cross-account patterns
          </h2>
          <ul className="text-body text-ink-800 mt-2 space-y-2">
            {patterns.map((c) => (
              <li key={c.id} className="border-border/80 rounded border bg-paper-100 px-3 py-2">
                <p className="font-medium text-ink-900">{c.title}</p>
                <p className="text-ink-600 text-sm">{c.note}</p>
              </li>
            ))}
          </ul>
        </section>
      ) : null}
      <section
        className="bg-paper-100 border-border rounded-lg border p-4"
        aria-labelledby="class-b"
      >
        <h2 id="class-b" className="text-foreground text-sm font-semibold">
          Class B solidification
        </h2>
        <p className="text-body text-ink-700 mt-1">
          Open the review queue to promote, demote, or defer pattern extractions (Epic 9).
        </p>
        <Link
          href="/solidification-review"
          className="text-evidence-700 focus-visible:ring-ring mt-3 inline-block text-sm font-medium underline-offset-2 hover:underline focus-visible:rounded focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-offset-2"
        >
          Go to solidification review
        </Link>
      </section>
    </div>
  );
}
