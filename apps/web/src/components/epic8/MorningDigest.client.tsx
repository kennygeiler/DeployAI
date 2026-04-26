"use client";

import { DigestEvidenceCard } from "./DigestEvidenceCard.client";
import { MORNING_DIGEST_RANKED_OUT, MORNING_DIGEST_TOP } from "@/lib/epic8/mock-digest";
import { useStrategistSurface } from "@/lib/epic8/strategist-surface-context";

export function MorningDigestClient() {
  const { agentDegraded } = useStrategistSurface();
  return (
    <div className="flex flex-col gap-8">
      <div>
        <h1 className="text-display text-ink-950 font-semibold tracking-tight">Morning digest</h1>
        <p className="text-body text-ink-600 mt-1 max-w-2xl">
          Phase-contextual priorities for today — three items (FR34). No loading shimmer on agent body
          text (UX-DR23).
        </p>
        {agentDegraded ? (
          <p className="text-ink-800 mt-2 max-w-2xl rounded-md border border-amber-600/30 bg-amber-50/80 px-3 py-2 text-sm">
            Agent ranking is paused; evidence below shows the last materialized sync from canonical
            memory only (FR46).
          </p>
        ) : null}
      </div>
      <div
        className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3"
        data-testid="morning-digest-top"
      >
        {MORNING_DIGEST_TOP.map((item) => (
          <DigestEvidenceCard key={item.id} item={item} headingLevel="h2" />
        ))}
      </div>
      <footer className="border-border rounded-lg border border-dashed p-4">
        <h2 className="text-foreground text-sm font-semibold">What I ranked out</h2>
        <ul className="text-body text-ink-700 mt-2 list-inside list-disc space-y-1">
          {MORNING_DIGEST_RANKED_OUT.map((o) => (
            <li key={o.id}>
              <span className="font-medium text-ink-900">{o.label}</span> — {o.reason}
            </li>
          ))}
        </ul>
      </footer>
    </div>
  );
}
