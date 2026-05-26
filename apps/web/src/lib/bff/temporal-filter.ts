"use client";

import * as React from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";

export type Section =
  | "insights"
  | "decisions"
  | "risks"
  | "stakeholders"
  | "systems"
  | "commitments";

export type DateRange = { from: Date | null; to: Date | null };

const ISO_DAY = /^\d{4}-\d{2}-\d{2}$/;

export function parseIsoDay(value: string | null | undefined): Date | null {
  if (typeof value !== "string" || !ISO_DAY.test(value)) return null;
  const d = new Date(`${value}T00:00:00.000Z`);
  return Number.isNaN(d.getTime()) ? null : d;
}

export function toIsoDay(d: Date): string {
  const y = d.getUTCFullYear();
  const m = String(d.getUTCMonth() + 1).padStart(2, "0");
  const day = String(d.getUTCDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

export function paramKey(section: Section, bound: "from" | "to"): string {
  return `${section}.${bound}`;
}

export function readRange(params: URLSearchParams, section: Section): DateRange {
  const from = parseIsoDay(params.get(paramKey(section, "from")));
  const to = parseIsoDay(params.get(paramKey(section, "to")));
  if (from && to && from.getTime() > to.getTime()) {
    return { from: to, to: from };
  }
  return { from, to };
}

export function writeRange(
  params: URLSearchParams,
  section: Section,
  next: DateRange,
): URLSearchParams {
  const out = new URLSearchParams(params.toString());
  const fromKey = paramKey(section, "from");
  const toKey = paramKey(section, "to");
  const ordered: DateRange =
    next.from && next.to && next.from.getTime() > next.to.getTime()
      ? { from: next.to, to: next.from }
      : next;
  if (ordered.from) {
    out.set(fromKey, toIsoDay(ordered.from));
  } else {
    out.delete(fromKey);
  }
  if (ordered.to) {
    out.set(toKey, toIsoDay(ordered.to));
  } else {
    out.delete(toKey);
  }
  return out;
}

export function filterByRange<T>(
  items: T[],
  getTimestamp: (item: T) => string,
  range: DateRange,
): T[] {
  if (!range.from && !range.to) return items;
  const fromMs = range.from ? range.from.getTime() : Number.NEGATIVE_INFINITY;
  const toMs = range.to ? range.to.getTime() + 24 * 60 * 60 * 1000 - 1 : Number.POSITIVE_INFINITY;
  return items.filter((item) => {
    const raw = getTimestamp(item);
    const ms = new Date(raw).getTime();
    if (Number.isNaN(ms)) return false;
    return ms >= fromMs && ms <= toMs;
  });
}

export function useTemporalFilter(section: Section): {
  range: DateRange;
  setRange: (next: DateRange) => void;
} {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();

  const range = React.useMemo(
    () => readRange(new URLSearchParams(searchParams?.toString() ?? ""), section),
    [searchParams, section],
  );

  const setRange = React.useCallback(
    (next: DateRange) => {
      if (!pathname) return;
      const out = writeRange(new URLSearchParams(searchParams?.toString() ?? ""), section, next);
      const qs = out.toString();
      router.replace(qs.length > 0 ? `${pathname}?${qs}` : pathname, { scroll: false });
    },
    [router, pathname, searchParams, section],
  );

  return { range, setRange };
}
