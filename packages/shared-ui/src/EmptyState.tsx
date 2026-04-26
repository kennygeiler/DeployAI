"use client";

import * as React from "react";
import { BookOpen, Sparkles } from "lucide-react";

import { cn } from "./lib/utils";

export type EmptyStateProps = {
  title: string;
  description: string;
  actionLabel: string;
  onAction: () => void;
  docsLabel?: string;
  docsUrl?: string;
  className?: string;
  id?: string;
};

/**
 * Authored empty surface (UX-DR22). No generic “no data” — always explains + next step + learn more.
 */
export function EmptyState({
  title,
  description,
  actionLabel,
  onAction,
  docsLabel = "Learn more in documentation",
  docsUrl,
  className: classNameProp,
  id: idProp,
}: EmptyStateProps) {
  const baseId = idProp ?? React.useId();
  const titleId = `${baseId}-title`;
  return (
    <section
      aria-labelledby={titleId}
      className={cn("rounded-lg border border-dashed border-border p-6 text-center", classNameProp)}
    >
      <Sparkles className="mx-auto size-8 text-ink-400" aria-hidden />
      <h2 id={titleId} className="mt-2 text-base font-semibold text-ink-900">
        {title}
      </h2>
      <p className="mt-1 text-sm text-ink-700">{description}</p>
      <div className="mt-4 flex flex-col items-center gap-2 sm:flex-row sm:justify-center">
        <button
          type="button"
          onClick={onAction}
          className="inline-flex h-9 items-center justify-center rounded-md border border-evidence-700/30 bg-evidence-700 px-4 text-sm font-medium text-paper-100 hover:bg-evidence-600"
        >
          {actionLabel}
        </button>
        {docsUrl ? (
          <a
            href={docsUrl}
            className="inline-flex items-center gap-1 text-sm text-evidence-800 underline-offset-2 hover:underline"
          >
            <BookOpen className="size-3.5" aria-hidden />
            {docsLabel}
          </a>
        ) : null}
      </div>
    </section>
  );
}
