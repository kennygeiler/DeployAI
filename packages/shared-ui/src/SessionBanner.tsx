"use client";

import * as React from "react";

import { cn } from "./lib/utils";

export type SessionBannerVariant = "break-glass" | "external-auditor";

function parseExpiresAt(expiresAt: Date | number | string): number {
  if (typeof expiresAt === "number") {
    return expiresAt;
  }
  if (typeof expiresAt === "string") {
    return new Date(expiresAt).getTime();
  }
  return expiresAt.getTime();
}

function formatClock(ms: number) {
  if (ms <= 0) {
    return "0:00";
  }
  const s = Math.floor(ms / 1000);
  const m = Math.floor(s / 60);
  const r = s % 60;
  return `${m}:${r.toString().padStart(2, "0")}`;
}

export type SessionBannerProps = {
  sessionId: string;
  variant: SessionBannerVariant;
  expiresAt: Date | number | string;
  className?: string;
  nowMs?: () => number;
};

const ANNOUNCE_EVERY_MS = 5 * 60 * 1000;

/**
 * Break-glass / external-auditor session strip (UX-DR42). Countdown each second (visual);
 * `aria-live="polite"` updates on a 5-minute cadence for screen readers.
 */
export function SessionBanner({
  sessionId,
  variant,
  expiresAt,
  className: classNameProp,
  nowMs = () => Date.now(),
}: SessionBannerProps) {
  const exp = parseExpiresAt(expiresAt);
  const [now, setNow] = React.useState(nowMs);
  const [polite, setPolite] = React.useState("");
  const label =
    variant === "break-glass" ? "Break-glass session" : "External auditor read-only session";

  React.useEffect(() => {
    const t = window.setInterval(() => {
      setNow(nowMs());
    }, 1000);
    return () => {
      window.clearInterval(t);
    };
  }, [nowMs]);

  const remaining = Math.max(0, exp - now);

  React.useEffect(() => {
    const tick = () => {
      const r = Math.max(0, exp - nowMs());
      setPolite(`${label} ${sessionId.slice(0, 8)}… ${formatClock(r)} remaining.`);
    };
    tick();
    const id = window.setInterval(tick, ANNOUNCE_EVERY_MS);
    return () => {
      window.clearInterval(id);
    };
  }, [exp, label, sessionId, nowMs]);

  return (
    <div
      className={cn(
        "w-full border-b px-4 py-2 text-sm",
        variant === "break-glass" && "border-amber-600/50 bg-amber-50/95 text-amber-950",
        variant === "external-auditor" && "border-evidence-700/25 bg-evidence-50/90 text-ink-900",
        classNameProp,
      )}
      role="region"
      aria-label={label}
    >
      <div className="mx-auto flex max-w-[1440px] flex-col gap-1 sm:flex-row sm:items-center sm:justify-between">
        <p className="font-medium">
          {label} <span className="font-mono text-xs opacity-90">{sessionId}</span>
        </p>
        <div>
          <span className="sr-only" role="status" aria-live="polite">
            {polite}
          </span>
          <p className="font-mono text-xs sm:text-sm" aria-hidden="true">
            Time left: {formatClock(remaining)}
          </p>
        </div>
      </div>
    </div>
  );
}
