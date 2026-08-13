"use client";

import * as React from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import type { GapAsk, GapAsksResponse } from "@/lib/bff/gap-ask-types";
import { invalidateCachedFetch, useCachedFetch } from "@/lib/hooks/useCachedFetch";

/**
 * Wave 5 GA2 — "Kenny asks": deterministic gap detection surfaced as
 * actionable ask-cards in the Brief's Needs-you region.
 *
 * The product thesis: instead of the user guessing what to upload next, the
 * system detects what the decision record is missing and asks for it
 * specifically. Asks come precomputed and pre-filtered from the BFF
 * (dismissed/snoozed ones never arrive); dismiss and snooze-7d persist by
 * deterministic ask id, so a recompute cannot resurrect a dismissed ask.
 *
 * Quiet by design: no asks (or an unavailable endpoint) renders nothing.
 */
export function KennyAsks({
  engagementId,
  onOpenCapture,
}: {
  engagementId: string;
  onOpenCapture: () => void;
}) {
  const asksKey = `/api/bff/engagements/${encodeURIComponent(engagementId)}/gap-asks`;
  const { data, error } = useCachedFetch<GapAsksResponse>(asksKey);
  const [busyId, setBusyId] = React.useState<string | null>(null);

  const act = React.useCallback(
    async (askId: string, action: "dismiss" | "snooze") => {
      setBusyId(askId);
      try {
        const r = await fetch(
          `/api/bff/engagements/${encodeURIComponent(engagementId)}/gap-asks/` +
            `${encodeURIComponent(askId)}/${action}`,
          {
            method: "POST",
            headers: { "content-type": "application/json" },
            body: JSON.stringify(action === "snooze" ? { days: 7 } : {}),
          },
        );
        if (!r.ok) {
          toast.error(
            action === "snooze" ? "Could not snooze the ask" : "Could not dismiss the ask",
          );
          return;
        }
        invalidateCachedFetch(asksKey);
      } finally {
        setBusyId(null);
      }
    },
    [engagementId, asksKey],
  );

  const asks = data?.asks ?? [];
  if (error || asks.length === 0) {
    // Quiet empty state — the Brief shows nothing when the record is whole.
    return null;
  }

  return (
    <section aria-labelledby="kenny-asks-heading" data-testid="kenny-asks" className="space-y-2">
      <h2 id="kenny-asks-heading" className="text-ink-800 text-sm font-semibold">
        Kenny asks
      </h2>
      <ul className="space-y-2">
        {asks.map((ask) => (
          <AskCard
            key={ask.id}
            ask={ask}
            busy={busyId === ask.id}
            onOpenCapture={onOpenCapture}
            onDismiss={() => void act(ask.id, "dismiss")}
            onSnooze={() => void act(ask.id, "snooze")}
          />
        ))}
      </ul>
    </section>
  );
}

function AskCard({
  ask,
  busy,
  onOpenCapture,
  onDismiss,
  onSnooze,
}: {
  ask: GapAsk;
  busy: boolean;
  onOpenCapture: () => void;
  onDismiss: () => void;
  onSnooze: () => void;
}) {
  return (
    <li
      data-testid={`kenny-ask-${ask.rule}`}
      className="space-y-1.5 rounded-card bg-surface p-3 shadow-card"
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 space-y-0.5">
          <p className="text-ink-800 text-sm font-medium">{ask.title}</p>
          <p className="text-ink-600 text-xs">{ask.why}</p>
        </div>
        <Button
          type="button"
          variant="ghost"
          size="sm"
          className="h-6 w-6 shrink-0 px-0 text-xs"
          aria-label={`Dismiss: ${ask.title}`}
          disabled={busy}
          onClick={onDismiss}
        >
          ×
        </Button>
      </div>
      <div className="flex flex-wrap items-center gap-2">
        {/* Every remedy currently routes through Capture. Forward asks will
            grow a "Copy deal address" CTA — the intake-address BFF endpoint
            lands with the intake-email lane. */}
        <Button
          type="button"
          size="sm"
          variant="outline"
          className="h-7 px-3 text-xs"
          disabled={busy}
          onClick={onOpenCapture}
        >
          Open Capture
        </Button>
        <Button
          type="button"
          size="sm"
          variant="ghost"
          className="h-7 px-2 text-xs"
          disabled={busy}
          onClick={onSnooze}
        >
          Snooze 7d
        </Button>
      </div>
    </li>
  );
}
