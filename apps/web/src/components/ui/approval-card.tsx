"use client";

/**
 * ApprovalCard — Beautiful UI component 04.
 *
 * Human-in-the-loop question the agent asks before acting: a question, a set
 * of option buttons, and accept/decline actions. Purely presentational —
 * selection state and submission are owned by the caller via callbacks (the
 * HITL wiring lands in a later ticket).
 */

import * as React from "react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export type ApprovalOption = {
  id: string;
  label: string;
  /** Optional secondary line under the label. */
  description?: string;
};

export type ApprovalCardProps = {
  /** The question the agent needs answered before acting. */
  question: string;
  options: ApprovalOption[];
  /** Controlled selection; highlight only, caller owns the state. */
  selectedId?: string | null;
  onSelect?: (id: string) => void;
  onAccept?: (selectedId: string | null) => void;
  onDecline?: () => void;
  acceptLabel?: string;
  declineLabel?: string;
  /** Disables every control (e.g. while a decision is submitting). */
  disabled?: boolean;
  className?: string;
};

function ApprovalCard({
  question,
  options,
  selectedId = null,
  onSelect,
  onAccept,
  onDecline,
  acceptLabel = "Accept",
  declineLabel = "Decline",
  disabled = false,
  className,
}: ApprovalCardProps) {
  return (
    <div
      data-slot="approval-card"
      role="group"
      aria-label={question}
      className={cn("rounded-card bg-surface p-4 shadow-card", className)}
    >
      <p className="text-sm font-medium text-ink">{question}</p>

      <div className="mt-3 flex flex-col gap-1.5" role="radiogroup" aria-label="Options">
        {options.map((option) => {
          const selected = option.id === selectedId;
          return (
            <button
              key={option.id}
              type="button"
              role="radio"
              aria-checked={selected}
              disabled={disabled}
              onClick={() => onSelect?.(option.id)}
              className={cn(
                "w-full rounded-control px-3 py-2 text-left text-sm transition-colors focus-visible:ring-2 focus-visible:ring-ring/50 focus-visible:outline-none disabled:pointer-events-none disabled:opacity-50",
                selected
                  ? "bg-accent-tint text-accent-ink shadow-hairline"
                  : "text-ink shadow-hairline hover:bg-hover",
              )}
            >
              <span className="font-medium">{option.label}</span>
              {option.description ? (
                <span className="mt-0.5 block text-xs text-ink-2">{option.description}</span>
              ) : null}
            </button>
          );
        })}
      </div>

      <div className="mt-4 flex items-center justify-end gap-2">
        <Button
          type="button"
          variant="ghost"
          size="sm"
          disabled={disabled}
          onClick={() => onDecline?.()}
        >
          {declineLabel}
        </Button>
        <Button type="button" size="sm" disabled={disabled} onClick={() => onAccept?.(selectedId)}>
          {acceptLabel}
        </Button>
      </div>
    </div>
  );
}

export { ApprovalCard };
