"use client";

import * as React from "react";

import { cn } from "./lib/utils";

export type ValidationQueueState = "unresolved" | "in-review" | "resolved" | "escalated";

export type ValidationQueueCardProps = {
  /** Single proposed fact (plain language, not a raw model dump). */
  proposedFact: string;
  /**
   * Usually one–three `CitationChip` elements; the host enforces list length.
   * @see Story 6.6 proposal shape
   */
  supportingEvidence: React.ReactNode;
  /** Human-readable confidence, e.g. "0.91" or "High (0.91)". */
  confidence: string;
  state: ValidationQueueState;
  onConfirm: () => void | Promise<void>;
  onModify: (reason: string) => void | Promise<void>;
  onReject: (reason: string) => void | Promise<void>;
  onDefer: () => void | Promise<void>;
  className?: string;
  id?: string;
  /** Disables the action row (e.g. submission in flight). */
  disabled?: boolean;
  /** Shown in `in-review` (e.g. "Assigned to you for review"). */
  inReviewHint?: string;
};

const fieldClass =
  "min-h-20 w-full rounded-md border border-border bg-paper-100 px-3 py-2 text-sm text-ink-900 shadow-xs " +
  "placeholder:text-ink-400 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring " +
  "disabled:cursor-not-allowed disabled:opacity-50";

/**
 * One validation / solidification queue item (UX-DR10, FR33, Story 6.6). `article` landmark;
 * **Modify** and **Reject** require a non-empty reason (FR33 / Oracle re-rank). All actions use
 * explicit `aria-label`s and stay in tab order. Terminal states: `resolved`, `escalated`.
 */
export function ValidationQueueCard({
  proposedFact,
  supportingEvidence,
  confidence,
  state: queueState,
  onConfirm,
  onModify,
  onReject,
  onDefer,
  className: classNameProp,
  id: idProp,
  disabled = false,
  inReviewHint = "Assigned to you for review.",
}: ValidationQueueCardProps) {
  const baseId = idProp ?? React.useId();
  const titleId = `${baseId}-title`;
  const reasonId = `${baseId}-reason`;
  const reasonErr = `${baseId}-reason-err`;
  const statusId = `${baseId}-status`;

  const [reason, setReason] = React.useState("");
  const [reasonError, setReasonError] = React.useState<string | null>(null);
  const [pending, setPending] = React.useState<"confirm" | "modify" | "reject" | "defer" | null>(
    null,
  );

  const withPending = async (
    kind: "confirm" | "modify" | "reject" | "defer",
    fn: () => void | Promise<void>,
  ) => {
    setPending(kind);
    try {
      await fn();
    } finally {
      setPending(null);
    }
  };

  const needsReason = () => {
    const t = reason.trim();
    if (t.length === 0) {
      setReasonError("Add a reason for the proposal team and Oracle re-rank.");
      return null;
    }
    setReasonError(null);
    return t;
  };

  const runWithReason = async (
    action: "modify" | "reject",
    fn: (r: string) => void | Promise<void>,
  ) => {
    const r = needsReason();
    if (r === null) {
      return;
    }
    await withPending(action, () => fn(r));
  };

  const actionLocked = disabled || queueState === "resolved" || queueState === "escalated";
  const showReason = queueState === "unresolved" || queueState === "in-review";
  const reasonInvalid = Boolean(reasonError);

  return (
    <article
      data-testid="validation-queue-card"
      aria-labelledby={titleId}
      className={cn(
        "max-w-[min(100%,40rem)] rounded-lg border border-border bg-paper-100 p-4 text-ink-900 shadow-sm",
        queueState === "in-review" &&
          "border-l-4 border-l-evidence-600 ring-1 ring-evidence-700/15",
        queueState === "escalated" && "ring-1 ring-amber-600/25",
        queueState === "resolved" && "opacity-90",
        classNameProp,
      )}
      data-validation-state={queueState}
    >
      {queueState === "in-review" ? (
        <p id={statusId} className="mb-2 text-xs font-medium text-evidence-800" role="status">
          {inReviewHint}
        </p>
      ) : null}
      {queueState === "resolved" ? (
        <p id={statusId} className="mb-2 text-sm font-medium text-ink-800" role="status">
          Resolved — this proposal is closed.
        </p>
      ) : null}
      {queueState === "escalated" ? (
        <p id={statusId} className="mb-2 text-sm font-medium text-amber-950" role="status">
          Escalated — awaiting chair review; actions are read-only.
        </p>
      ) : null}

      <h2 id={titleId} className="text-base font-semibold text-ink-900">
        Proposed fact
      </h2>
      <p className="mt-1 text-sm leading-relaxed text-ink-800">{proposedFact}</p>

      <h3 className="mt-4 text-sm font-medium text-ink-900">Supporting evidence</h3>
      <div className="mt-2 flex flex-col gap-2">{supportingEvidence}</div>

      <p className="mt-3 text-sm text-ink-700">
        <span className="font-medium text-ink-900">Confidence:</span> {confidence}
      </p>

      {showReason && !actionLocked ? (
        <div className="mt-4 space-y-1">
          <label htmlFor={reasonId} className="text-sm font-medium text-ink-900">
            Response reason <span className="text-ink-500">(required for modify and reject)</span>
          </label>
          <textarea
            id={reasonId}
            name="responseReason"
            className={cn(fieldClass, reasonInvalid && "border-rose-600")}
            value={reason}
            onChange={(e) => {
              setReason(e.target.value);
              if (reasonError) {
                setReasonError(null);
              }
            }}
            rows={3}
            aria-invalid={reasonInvalid ? "true" : "false"}
            aria-describedby={reasonError ? reasonErr : undefined}
            disabled={disabled}
            placeholder="Explain adjustments, or why you are rejecting. Oracle uses this for re-ranking (FR33)."
          />
          {reasonError ? (
            <p id={reasonErr} className="text-xs text-rose-700" role="alert">
              {reasonError}
            </p>
          ) : null}
        </div>
      ) : null}

      {actionLocked && queueState !== "resolved" && queueState !== "escalated" ? (
        <p className="mt-4 text-sm text-ink-500">Actions disabled.</p>
      ) : null}

      {!actionLocked && showReason ? (
        <div
          className="mt-4 flex flex-wrap items-center gap-2 border-t border-border pt-4"
          role="group"
          aria-label="Queue actions"
        >
          <button
            type="button"
            className="inline-flex h-9 min-w-[2.75rem] items-center justify-center rounded-md border border-evidence-700/30 bg-evidence-700 px-3 text-sm font-medium text-paper-100 hover:bg-evidence-600 disabled:opacity-50"
            aria-label="Confirm proposal"
            disabled={disabled || pending !== null}
            onClick={() => {
              void withPending("confirm", () => onConfirm());
            }}
          >
            {pending === "confirm" ? "…" : "Confirm"}
          </button>
          <button
            type="button"
            className="inline-flex h-9 min-w-[2.75rem] items-center justify-center rounded-md border border-border bg-paper-200 px-3 text-sm font-medium text-ink-900 hover:bg-paper-300 disabled:opacity-50"
            aria-label="Modify proposal"
            disabled={disabled || pending !== null}
            onClick={() => {
              void runWithReason("modify", onModify);
            }}
          >
            {pending === "modify" ? "…" : "Modify"}
          </button>
          <button
            type="button"
            className="inline-flex h-9 min-w-[2.75rem] items-center justify-center rounded-md border border-rose-600/30 bg-rose-50/90 px-3 text-sm font-medium text-ink-900 hover:bg-rose-100 disabled:opacity-50"
            aria-label="Reject proposal"
            disabled={disabled || pending !== null}
            onClick={() => {
              void runWithReason("reject", onReject);
            }}
          >
            {pending === "reject" ? "…" : "Reject"}
          </button>
          <button
            type="button"
            className="inline-flex h-9 min-w-[2.75rem] items-center justify-center rounded-md border border-dashed border-border bg-transparent px-3 text-sm font-medium text-ink-800 hover:bg-paper-200/80 disabled:opacity-50"
            aria-label="Defer proposal"
            disabled={disabled || pending !== null}
            onClick={() => {
              setReasonError(null);
              void withPending("defer", () => onDefer());
            }}
          >
            {pending === "defer" ? "…" : "Defer"}
          </button>
        </div>
      ) : null}
    </article>
  );
}
