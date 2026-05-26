"use client";

import * as React from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { type DateRange, parseIsoDay, toIsoDay } from "@/lib/bff/temporal-filter";

type Props = {
  value: DateRange;
  onChange: (next: DateRange) => void;
  label?: string;
  idPrefix: string;
};

export function DateRangeFilter({ value, onChange, label, idPrefix }: Props) {
  const fromId = `${idPrefix}-from`;
  const toId = `${idPrefix}-to`;

  const handleFrom = React.useCallback(
    (raw: string) => {
      const next = raw === "" ? null : parseIsoDay(raw);
      // Auto-swap: if the new from is after the existing to, swap.
      if (next && value.to && next.getTime() > value.to.getTime()) {
        onChange({ from: value.to, to: next });
        return;
      }
      onChange({ from: next, to: value.to });
    },
    [onChange, value.to],
  );

  const handleTo = React.useCallback(
    (raw: string) => {
      const next = raw === "" ? null : parseIsoDay(raw);
      if (next && value.from && next.getTime() < value.from.getTime()) {
        onChange({ from: next, to: value.from });
        return;
      }
      onChange({ from: value.from, to: next });
    },
    [onChange, value.from],
  );

  const clear = React.useCallback(() => {
    onChange({ from: null, to: null });
  }, [onChange]);

  const hasFilter = value.from !== null || value.to !== null;

  return (
    <div className="flex flex-wrap items-end gap-2" role="group" aria-label={label ?? "Date range"}>
      <div className="grid gap-1">
        <label className="text-ink-600 text-xs" htmlFor={fromId}>
          From
        </label>
        <Input
          id={fromId}
          type="date"
          className="h-7 w-[10rem] text-xs"
          value={value.from ? toIsoDay(value.from) : ""}
          onChange={(e) => handleFrom(e.target.value)}
        />
      </div>
      <div className="grid gap-1">
        <label className="text-ink-600 text-xs" htmlFor={toId}>
          To
        </label>
        <Input
          id={toId}
          type="date"
          className="h-7 w-[10rem] text-xs"
          value={value.to ? toIsoDay(value.to) : ""}
          onChange={(e) => handleTo(e.target.value)}
        />
      </div>
      {hasFilter ? (
        <Button
          type="button"
          size="sm"
          variant="outline"
          className="h-7 px-2 text-xs"
          onClick={clear}
        >
          Clear
        </Button>
      ) : null}
    </div>
  );
}
