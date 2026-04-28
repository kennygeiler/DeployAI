"use client";

import * as React from "react";

import { cn } from "./lib/utils";

export type OverrideEvidenceOption = { id: string; label: string };

export type OverrideSubmitPayload = {
  whatChanged: string;
  why: string;
  evidenceNodeIds: string[];
  learningId?: string;
  privateAnnotation?: string;
};

export type OverrideComposerProps = {
  /** Canonical memory nodes the user can cite (stub picker until Epic 10 wiring). */
  evidenceOptions: readonly OverrideEvidenceOption[];
  /**
   * Stub list of surfaces that would receive propagation (graph traversal is future work).
   * @default Built-in Epic 8 surface names for preview copy.
   */
  affectedSurfaces?: readonly string[];
  onSubmit: (payload: OverrideSubmitPayload) => void | Promise<void>;
  className?: string;
  id?: string;
  disabled?: boolean;
  /** When true, require a UUID learning id (Epic 10.2 CP contract). */
  withLearningId?: boolean;
  /** Optional private note stored encrypted (Epic 10.5). */
  withPrivateAnnotation?: boolean;
};

const DEFAULT_AFFECTED = [
  "Morning Digest",
  "In-Meeting alert",
  "Evening Synthesis",
  "Phase & task tracking",
] as const;

const fieldClass =
  "flex min-h-[2.5rem] w-full rounded-md border border-border bg-paper-100 px-3 py-2 text-sm text-ink-900 shadow-xs transition-colors " +
  "placeholder:text-ink-400 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring " +
  "disabled:cursor-not-allowed disabled:opacity-50";

/**
 * Inline override form (UX-DR8, FR49). Three fields + multi-select evidence; propagation
 * preview is a **stub** until canonical memory graph APIs exist.
 */
export function OverrideComposer({
  evidenceOptions,
  affectedSurfaces = DEFAULT_AFFECTED,
  onSubmit,
  className: classNameProp,
  id: idProp,
  disabled = false,
  withLearningId = false,
  withPrivateAnnotation = false,
}: OverrideComposerProps) {
  const formId = idProp ?? React.useId();
  const whatId = `${formId}-what`;
  const whyId = `${formId}-why`;
  const errWhat = `${formId}-err-what`;
  const errWhy = `${formId}-err-why`;
  const errEv = `${formId}-err-evidence`;
  const errLid = `${formId}-err-learning`;
  const errPriv = `${formId}-err-private`;
  const liveSummary = `${formId}-summary`;

  const [learningId, setLearningId] = React.useState("");
  const [privateNote, setPrivateNote] = React.useState("");
  const [what, setWhat] = React.useState("");
  const [why, setWhy] = React.useState("");
  const [selected, setSelected] = React.useState<Set<string>>(() => new Set());
  const [touched, setTouched] = React.useState({
    what: false,
    why: false,
    evidence: false,
    learningId: false,
    privateNote: false,
  });
  const [submitting, setSubmitting] = React.useState(false);
  const [formError, setFormError] = React.useState<string | null>(null);
  const [status, setStatus] = React.useState<"idle" | "success" | "error">("idle");
  /** UX-DR24 — persistent until strategist dismisses (not auto-dismissed). */
  const [confirmationDismissed, setConfirmationDismissed] = React.useState(false);

  const whatErr = touched.what && what.trim().length === 0 ? "Describe what changed." : undefined;
  const whyErr =
    touched.why && why.trim().length === 0
      ? "Explain why the override is justified."
      : touched.why && why.trim().length < 20
        ? "Justification must be at least 20 characters (Epic 10.2)."
        : undefined;
  const evErr =
    touched.evidence && selected.size === 0 ? "Select at least one evidence item." : undefined;
  const uuidRe = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
  const lidErr =
    withLearningId && touched.learningId && !uuidRe.test(learningId.trim())
      ? "Enter the solidified learning UUID."
      : undefined;
  const privErr =
    withPrivateAnnotation && touched.privateNote && privateNote.length > 8000
      ? "Private note must be 8000 characters or fewer."
      : undefined;
  const errorCount = [whatErr, whyErr, evErr, lidErr, privErr].filter(Boolean).length;

  const formRef = React.useRef<HTMLFormElement | null>(null);
  const runSubmitRef = React.useRef<() => Promise<void>>(() => Promise.resolve());

  const runSubmit = async () => {
    setTouched({
      what: true,
      why: true,
      evidence: true,
      learningId: withLearningId,
      privateNote: withPrivateAnnotation,
    });
    setFormError(null);
    if (
      what.trim().length === 0 ||
      why.trim().length < 20 ||
      selected.size === 0 ||
      (withLearningId && !uuidRe.test(learningId.trim())) ||
      (withPrivateAnnotation && privateNote.length > 8000)
    ) {
      return;
    }
    setSubmitting(true);
    setStatus("idle");
    try {
      await onSubmit({
        whatChanged: what.trim(),
        why: why.trim(),
        evidenceNodeIds: Array.from(selected),
        ...(withLearningId ? { learningId: learningId.trim() } : {}),
        ...(withPrivateAnnotation && privateNote.trim()
          ? { privateAnnotation: privateNote.trim() }
          : {}),
      });
      setStatus("success");
      setConfirmationDismissed(false);
    } catch {
      setStatus("error");
      setFormError("Override could not be submitted. Try again.");
    } finally {
      setSubmitting(false);
    }
  };
  runSubmitRef.current = runSubmit;

  React.useEffect(() => {
    const onDocKeyDown = (e: KeyboardEvent) => {
      if (disabled || submitting) {
        return;
      }
      if (e.key !== "Enter" || (!e.metaKey && !e.ctrlKey)) {
        return;
      }
      const t = e.target;
      if (!(t instanceof Node) || !formRef.current?.contains(t)) {
        return;
      }
      e.preventDefault();
      void runSubmitRef.current();
    };
    document.addEventListener("keydown", onDocKeyDown, true);
    return () => {
      document.removeEventListener("keydown", onDocKeyDown, true);
    };
  }, [disabled, submitting]);

  const onFormSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    void runSubmit();
  };

  return (
    <form
      ref={formRef}
      id={formId}
      className={cn("grid gap-4 md:grid-cols-2 md:items-start", classNameProp)}
      onSubmit={onFormSubmit}
      aria-busy={submitting}
      noValidate
    >
      {errorCount > 0 ? (
        <div
          id={liveSummary}
          role="alert"
          aria-live="assertive"
          className="md:col-span-2 rounded-md border border-rose-600/30 bg-rose-50/80 px-3 py-2 text-sm text-ink-800"
        >
          {errorCount} field{errorCount === 1 ? "" : "s"} need attention before you can submit.
        </div>
      ) : null}
      {formError ? (
        <div
          className="md:col-span-2 rounded-md border border-rose-600/30 bg-rose-50/80 px-3 py-2 text-sm"
          role="status"
        >
          {formError}
        </div>
      ) : null}
      {status === "success" && !confirmationDismissed ? (
        <div
          className="md:col-span-2 flex flex-col gap-2 rounded-md border border-evidence-700/25 bg-evidence-50/80 px-3 py-2 text-sm text-ink-900"
          role="status"
          data-testid="override-confirmation-chip"
        >
          <div className="flex flex-wrap items-start justify-between gap-2">
            <p>
              <span className="font-medium text-evidence-800">Override recorded.</span> Propagation
              preview is shown in the sidecar; this confirmation stays until you dismiss it
              (UX-DR24).
            </p>
            <button
              type="button"
              className="text-evidence-900 hover:text-evidence-700 shrink-0 text-xs font-medium underline underline-offset-2"
              onClick={() => {
                setConfirmationDismissed(true);
              }}
            >
              Dismiss
            </button>
          </div>
        </div>
      ) : null}

      <div className="flex min-w-0 flex-col gap-4">
        {withLearningId ? (
          <div className="space-y-2">
            <label htmlFor={`${formId}-learning`} className="text-sm font-medium text-ink-900">
              Learning id <span className="text-rose-700">*</span>
            </label>
            <input
              id={`${formId}-learning`}
              name="learningId"
              value={learningId}
              onChange={(e) => {
                setLearningId(e.target.value);
              }}
              onBlur={() => {
                setTouched((t) => ({ ...t, learningId: true }));
              }}
              className={cn(fieldClass, "min-h-10", lidErr && "border-rose-600")}
              aria-invalid={lidErr ? "true" : "false"}
              aria-describedby={lidErr ? errLid : undefined}
              disabled={disabled || submitting}
              autoComplete="off"
              placeholder="Solidified learning UUID"
            />
            {lidErr ? (
              <p id={errLid} className="text-xs text-rose-700">
                {lidErr}
              </p>
            ) : null}
          </div>
        ) : null}
        <div className="space-y-2">
          <label htmlFor={whatId} className="text-sm font-medium text-ink-900">
            What changed <span className="text-rose-700">*</span>
          </label>
          <textarea
            id={whatId}
            name="whatChanged"
            required
            value={what}
            onChange={(e) => {
              setWhat(e.target.value);
            }}
            onBlur={() => {
              setTouched((t) => ({ ...t, what: true }));
            }}
            className={cn(fieldClass, "min-h-24", whatErr && "border-rose-600")}
            aria-invalid={whatErr ? "true" : "false"}
            aria-describedby={whatErr ? errWhat : undefined}
            disabled={disabled || submitting}
            autoComplete="off"
          />
          {whatErr ? (
            <p id={errWhat} className="text-xs text-rose-700">
              {whatErr}
            </p>
          ) : null}
        </div>

        <div className="space-y-2">
          <label htmlFor={whyId} className="text-sm font-medium text-ink-900">
            Why (justification) <span className="text-rose-700">*</span>
          </label>
          <textarea
            id={whyId}
            name="why"
            required
            value={why}
            onChange={(e) => {
              setWhy(e.target.value);
            }}
            onBlur={() => {
              setTouched((t) => ({ ...t, why: true }));
            }}
            className={cn(fieldClass, "min-h-24", whyErr && "border-rose-600")}
            aria-invalid={whyErr ? "true" : "false"}
            aria-describedby={whyErr ? errWhy : undefined}
            disabled={disabled || submitting}
            autoComplete="off"
          />
          {whyErr ? (
            <p id={errWhy} className="text-xs text-rose-700">
              {whyErr}
            </p>
          ) : null}
        </div>

        <fieldset
          className="space-y-2 border-0 p-0"
          disabled={disabled || submitting}
          onBlur={() => {
            setTouched((t) => ({ ...t, evidence: true }));
          }}
        >
          <legend className="text-sm font-medium text-ink-900">
            Evidence <span className="text-rose-700">*</span>
          </legend>
          <p className="text-xs text-ink-600">
            Select one or more memory nodes. Cmd+Enter submits.
          </p>
          <ul className="max-h-40 space-y-1 overflow-y-auto rounded-md border border-border p-2">
            {evidenceOptions.length === 0 ? (
              <li className="text-sm text-ink-500">No evidence nodes available.</li>
            ) : (
              evidenceOptions.map((o) => {
                const checked = selected.has(o.id);
                return (
                  <li key={o.id} className="flex min-h-8 items-center gap-2 text-sm">
                    <input
                      type="checkbox"
                      id={`${formId}-ev-${o.id}`}
                      className="size-6 shrink-0 cursor-pointer accent-evidence-700"
                      checked={checked}
                      onChange={() => {
                        setTouched((t) => ({ ...t, evidence: true }));
                        setSelected((s) => {
                          const n = new Set(s);
                          if (n.has(o.id)) {
                            n.delete(o.id);
                          } else {
                            n.add(o.id);
                          }
                          return n;
                        });
                      }}
                    />
                    <label htmlFor={`${formId}-ev-${o.id}`} className="min-w-0">
                      {o.label}
                    </label>
                  </li>
                );
              })
            )}
          </ul>
          {evErr ? (
            <p id={errEv} className="text-xs text-rose-700">
              {evErr}
            </p>
          ) : null}
        </fieldset>

        {withPrivateAnnotation ? (
          <div className="space-y-2">
            <label htmlFor={`${formId}-private`} className="text-sm font-medium text-ink-900">
              Private note (author-only)
            </label>
            <p className="text-xs text-ink-600">
              Encrypted at rest; successor strategists cannot read this text (Epic 10.5).
            </p>
            <textarea
              id={`${formId}-private`}
              name="privateAnnotation"
              value={privateNote}
              onChange={(e) => {
                setPrivateNote(e.target.value);
              }}
              onBlur={() => {
                setTouched((t) => ({ ...t, privateNote: true }));
              }}
              className={cn(fieldClass, "min-h-20", privErr && "border-rose-600")}
              aria-invalid={privErr ? "true" : "false"}
              aria-describedby={privErr ? errPriv : undefined}
              disabled={disabled || submitting}
              autoComplete="off"
              placeholder="Optional — visible only to you (and platform break-glass policy)."
            />
            {privErr ? (
              <p id={errPriv} className="text-xs text-rose-700">
                {privErr}
              </p>
            ) : null}
          </div>
        ) : null}

        <div className="flex gap-2">
          <button
            type="submit"
            className="inline-flex h-9 items-center justify-center rounded-md border border-evidence-700/30 bg-evidence-700 px-4 text-sm font-medium text-paper-100 shadow-sm hover:bg-evidence-600 disabled:opacity-50"
            disabled={disabled || submitting}
          >
            {submitting ? "Submitting…" : "Submit override"}
          </button>
        </div>
      </div>

      <aside
        className="rounded-md border border-border bg-muted/30 p-3 text-sm text-ink-800"
        aria-label="Propagation preview"
      >
        <h3 className="font-medium text-ink-900">Propagation preview</h3>
        <p className="mt-1 text-xs text-ink-600">
          Surfaces that typically receive downstream updates when this override is applied (pilot
          preview list; graph-backed resolution follows).
        </p>
        <ul className="mt-2 list-inside list-disc space-y-0.5">
          {affectedSurfaces.map((s) => (
            <li key={s}>{s}</li>
          ))}
        </ul>
      </aside>
    </form>
  );
}
