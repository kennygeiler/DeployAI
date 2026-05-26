"use client";

import * as React from "react";

import { cn } from "@/lib/utils";

type Props = {
  value: string | null | undefined;
  prefix?: string;
  fallback?: string;
  className?: string;
};

const MINUTE = 60_000;
const HOUR = 60 * MINUTE;
const DAY = 24 * HOUR;
const WEEK = 7 * DAY;

const rtf = new Intl.RelativeTimeFormat("en", { numeric: "always", style: "narrow" });

export function formatRelative(value: string, now: Date = new Date()): string {
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) {
    return value;
  }
  const diffMs = now.getTime() - d.getTime();
  const absMs = Math.abs(diffMs);
  if (absMs < MINUTE) {
    return "just now";
  }
  if (absMs < HOUR) {
    const mins = Math.round(diffMs / MINUTE);
    return rtf.format(-mins, "minute");
  }
  if (absMs < DAY) {
    const hrs = Math.round(diffMs / HOUR);
    return rtf.format(-hrs, "hour");
  }
  if (absMs < WEEK) {
    const days = Math.round(diffMs / DAY);
    return rtf.format(-days, "day");
  }
  const sameYear = d.getUTCFullYear() === now.getUTCFullYear();
  return d.toLocaleString("en-US", {
    month: "short",
    day: "numeric",
    year: sameYear ? undefined : "numeric",
    timeZone: "UTC",
  });
}

function subscribeMinute(callback: () => void): () => void {
  if (typeof window === "undefined") return () => {};
  const id = window.setInterval(callback, MINUTE);
  return () => window.clearInterval(id);
}
function getNowMs(): number {
  return Date.now();
}
function getServerSnapshot(): number {
  // 0 keeps SSR text deterministic — the formatter falls back to the parsed
  // date itself, so the first paint matches what the server emitted.
  return 0;
}

export function TimestampLabel({ value, prefix, fallback = "unknown", className }: Props) {
  const parsed = React.useMemo(() => {
    if (typeof value !== "string" || value.length === 0) return null;
    const d = new Date(value);
    return Number.isNaN(d.getTime()) ? null : d;
  }, [value]);

  const nowMs = React.useSyncExternalStore(subscribeMinute, getNowMs, getServerSnapshot);

  if (!parsed) {
    const label = prefix ? `${prefix} ${fallback}` : fallback;
    return (
      <span className={cn("text-ink-600 text-xs", className)} aria-label={label}>
        {label}
      </span>
    );
  }

  const iso = parsed.toISOString();
  const now = nowMs === 0 ? parsed : new Date(nowMs);
  const relative = formatRelative(iso, now);
  const visible = prefix ? `${prefix} ${relative}` : relative;

  // Plain `<time title>` instead of Radix Tooltip — the native title tooltip
  // works everywhere (no portal/provider needed) and avoids Radix Tooltip
  // rendering errors observed inside jsdom on CI.
  return (
    <time dateTime={iso} title={iso} className={cn("text-ink-600 cursor-help text-xs", className)}>
      {visible}
    </time>
  );
}
