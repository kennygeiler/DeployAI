"use client";

import * as React from "react";
import { ExternalLink, RefreshCw } from "lucide-react";

import { cn } from "./lib/utils";

export type AgentOutageBannerVariant = "informational" | "alert" | "resolved";

export type AgentOutageBannerProps = {
  agentName: string;
  /** Plain-language; not alarmist for informational. */
  message: string;
  variant: AgentOutageBannerVariant;
  /** Optional status / health page. */
  statusPageUrl?: string;
  statusPageLabel?: string;
  /** Show retry affordance in copy. */
  retryAvailable?: boolean;
  /** e.g. "ETA ~2 min" */
  etaText?: string;
  onRetry?: () => void;
  className?: string;
};

/**
 * Degraded / outage callout (UX-DR12, FR46, NFR11). Amber signal palette — not destructive red.
 * `informational` + `resolved` use `role="status"`; `alert` uses `role="alert"`.
 */
export function AgentOutageBanner({
  agentName,
  message,
  variant,
  statusPageUrl,
  statusPageLabel = "Status page",
  retryAvailable = false,
  etaText,
  onRetry,
  className: classNameProp,
}: AgentOutageBannerProps) {
  const isAlert = variant === "alert";

  return (
    <div
      role={isAlert ? "alert" : "status"}
      className={cn(
        "w-full border-b border-amber-700/40 bg-amber-50/95 px-4 py-3 text-ink-900",
        variant === "resolved" && "border-emerald-700/30 bg-emerald-50/90",
        classNameProp,
      )}
      data-agent-outage={variant}
    >
      <div className="mx-auto flex max-w-[1440px] flex-col gap-2 md:flex-row md:items-center md:justify-between">
        <div className="min-w-0 text-sm">
          <p className="font-medium text-ink-900">
            {variant === "resolved" ? "All clear — " : null}
            {agentName}
            {variant === "resolved" ? "" : " — degraded"}
          </p>
          <p className="mt-0.5 text-ink-800">{message}</p>
          {etaText ? <p className="mt-1 text-xs text-ink-700">ETA: {etaText}</p> : null}
        </div>
        <div className="flex flex-shrink-0 flex-wrap items-center gap-3">
          {retryAvailable && onRetry && variant !== "resolved" ? (
            <button
              type="button"
              onClick={onRetry}
              className="inline-flex h-9 items-center gap-1.5 rounded-md border border-amber-700/30 bg-paper-100 px-3 text-sm font-medium text-ink-900 hover:bg-amber-100/80"
              aria-label={`Retry ${agentName}`}
            >
              <RefreshCw className="size-3.5" aria-hidden />
              Retry
            </button>
          ) : null}
          {statusPageUrl ? (
            <a
              href={statusPageUrl}
              className="inline-flex h-9 items-center gap-1 text-sm font-medium text-evidence-800 underline-offset-2 hover:underline"
            >
              {statusPageLabel}
              <ExternalLink className="size-3.5" aria-hidden />
            </a>
          ) : null}
        </div>
      </div>
    </div>
  );
}
