"use client";

import * as React from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";

import { Button } from "@/components/ui/button";

/**
 * Phase F3.c — horizontal time slider above the matrix view. Snaps to days,
 * writes `?at=YYYY-MM-DD` to the URL, defaults to "live" (no `at`). Pairs
 * with the F3.b CP snapshot endpoint via the matrix-snapshot BFF route.
 */

const DAY_MS = 24 * 60 * 60 * 1000;
const DEFAULT_WINDOW_DAYS = 90;

function toIsoDay(d: Date): string {
  const y = d.getUTCFullYear();
  const m = String(d.getUTCMonth() + 1).padStart(2, "0");
  const day = String(d.getUTCDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

function parseIsoDay(s: string): Date | null {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(s)) return null;
  const d = new Date(`${s}T00:00:00Z`);
  return Number.isNaN(d.getTime()) ? null : d;
}

function dayDiff(a: Date, b: Date): number {
  return Math.round((a.getTime() - b.getTime()) / DAY_MS);
}

export function MatrixTimeSlider({
  earliestDate,
  todayOverride,
}: {
  earliestDate?: string;
  todayOverride?: string;
}) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const atParam = searchParams?.get("at") ?? null;

  const today = React.useMemo(() => {
    const t = todayOverride ? parseIsoDay(todayOverride) : new Date();
    if (!t) return new Date();
    return new Date(Date.UTC(t.getUTCFullYear(), t.getUTCMonth(), t.getUTCDate()));
  }, [todayOverride]);

  const earliest = React.useMemo(() => {
    const e = earliestDate ? parseIsoDay(earliestDate) : null;
    if (e) return e;
    return new Date(today.getTime() - DEFAULT_WINDOW_DAYS * DAY_MS);
  }, [earliestDate, today]);

  const totalDays = Math.max(1, dayDiff(today, earliest));
  const parsedAt = atParam ? parseIsoDay(atParam) : null;
  const selectedDayIndex = parsedAt
    ? Math.min(totalDays, Math.max(0, dayDiff(parsedAt, earliest)))
    : totalDays;
  const isLive = !atParam;

  const pushAt = React.useCallback(
    (next: string | null) => {
      if (!pathname) return;
      const params = new URLSearchParams(searchParams?.toString() ?? "");
      if (next == null) {
        params.delete("at");
      } else {
        params.set("at", next);
      }
      const qs = params.toString();
      router.replace(qs.length > 0 ? `${pathname}?${qs}` : pathname, { scroll: false });
    },
    [router, pathname, searchParams],
  );

  const handleChange = React.useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const idx = Number.parseInt(e.target.value, 10);
      if (Number.isNaN(idx)) return;
      if (idx >= totalDays) {
        pushAt(null);
        return;
      }
      const next = new Date(earliest.getTime() + idx * DAY_MS);
      pushAt(toIsoDay(next));
    },
    [pushAt, earliest, totalDays],
  );

  const selectedLabel = isLive ? "Live" : parsedAt ? toIsoDay(parsedAt) : toIsoDay(today);

  return (
    <div
      className="border-border bg-paper-50 flex flex-wrap items-center gap-3 rounded-lg border p-3"
      data-testid="matrix-time-slider"
    >
      <label htmlFor="matrix-time-slider-input" className="text-ink-700 text-xs font-semibold">
        Matrix as of
      </label>
      <span
        className="text-ink-800 min-w-[5rem] font-mono text-xs"
        data-testid="matrix-time-slider-value"
      >
        {selectedLabel}
      </span>
      <input
        id="matrix-time-slider-input"
        type="range"
        min={0}
        max={totalDays}
        step={1}
        value={selectedDayIndex}
        onChange={handleChange}
        aria-label="Matrix snapshot date"
        aria-valuetext={selectedLabel}
        className="flex-1 min-w-[8rem]"
      />
      <span className="text-ink-500 hidden text-[10px] uppercase sm:inline">
        {toIsoDay(earliest)} — today
      </span>
      {!isLive ? (
        <Button
          type="button"
          size="sm"
          variant="outline"
          className="h-7 px-3 text-xs"
          onClick={() => pushAt(null)}
        >
          Return to live
        </Button>
      ) : null}
    </div>
  );
}
