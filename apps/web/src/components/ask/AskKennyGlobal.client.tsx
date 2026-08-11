"use client";

import * as React from "react";

import { OracleChat } from "@/components/engagements/OracleChat.client";
import { Button } from "@/components/ui/button";
import type { Engagement } from "@/lib/bff/engagement-types";
import { useCachedFetch } from "@/lib/hooks/useCachedFetch";

/**
 * Wave 2.5 U10 — global Kenny at /ask.
 *
 * One place to ask questions without first navigating a deal: pick an
 * engagement scope chip, and the existing chat surface mounts for it.
 * Cross-engagement synthesis is deliberately out of scope until Wave 3 —
 * every answer stays grounded in a single engagement's ledger.
 */
export function AskKennyGlobal() {
  const { data, error, pending } = useCachedFetch<{ engagements?: Engagement[] }>(
    "/api/bff/engagements",
  );
  const engagements = React.useMemo(() => data?.engagements ?? [], [data]);
  // Default scope is the first engagement; a chip click overrides it.
  const [pickedId, setPickedId] = React.useState<string | null>(null);
  const selectedId = pickedId ?? engagements[0]?.id ?? null;

  return (
    <div className="max-w-5xl space-y-4">
      <div>
        <h1 className="text-display text-ink-950 font-semibold tracking-tight">Ask Kenny</h1>
        <p className="text-body text-ink-600 mt-1 max-w-2xl">
          Ask about any deal — answers are grounded in that engagement&apos;s ledger with citations.
          Pick a deal to scope the conversation; cross-deal questions arrive in a later wave.
        </p>
      </div>

      {error ? <p className="text-red-ink text-sm">{error}</p> : null}
      {pending ? <p className="text-ink-600 text-sm">Loading engagements…</p> : null}

      {!pending && engagements.length === 0 && !error ? (
        <p className="text-ink-600 text-sm" data-testid="ask-empty">
          No engagements to ask about yet. Kenny answers questions per deal — run the onboarding
          wizard to seed your first engagement, then come back and ask what changed.
        </p>
      ) : null}

      {engagements.length > 0 ? (
        <>
          <ul className="flex flex-wrap gap-1.5" aria-label="Engagement scope">
            {engagements.map((e) => {
              const active = e.id === selectedId;
              return (
                <li key={e.id}>
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    onClick={() => setPickedId(e.id)}
                    aria-pressed={active}
                    data-testid={`ask-scope-${e.id}`}
                    className={
                      "h-auto rounded-full px-3 py-1 text-sm shadow-hairline transition-colors " +
                      (active
                        ? "bg-surface font-medium text-ink shadow-btn hover:bg-surface"
                        : "bg-hover text-ink-600 hover:bg-hover-2 hover:text-ink")
                    }
                  >
                    {e.name}
                  </Button>
                </li>
              );
            })}
          </ul>
          {selectedId ? (
            <OracleChat key={selectedId} engagementId={selectedId} variant="embedded" />
          ) : null}
        </>
      ) : null}
    </div>
  );
}
