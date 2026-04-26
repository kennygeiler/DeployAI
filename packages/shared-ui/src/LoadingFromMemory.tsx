"use client";

import * as React from "react";
import { Loader2 } from "lucide-react";

import { cn } from "./lib/utils";

export type LoadingFromMemoryProps = {
  label?: string;
  /** After initial chip, show progressive content (e.g. first row of results). */
  children?: React.ReactNode;
  className?: string;
};

/**
 * Explicit “loading from memory” affordance (UX-DR23). **No** shimmer on agent text — optional
 * `children` render as items arrive; chrome-only shimmer belongs in the host layout.
 */
export function LoadingFromMemory({
  label = "Loading from memory…",
  children,
  className: classNameProp,
}: LoadingFromMemoryProps) {
  return (
    <div className={cn("space-y-3", classNameProp)}>
      <p
        role="status"
        className="inline-flex items-center gap-2 rounded-md border border-border bg-paper-100 px-3 py-1.5 text-sm text-ink-800"
      >
        <Loader2 className="size-4 shrink-0 animate-spin text-evidence-700" aria-hidden />
        {label}
      </p>
      {children ? <div className="min-h-[1rem]">{children}</div> : null}
    </div>
  );
}
