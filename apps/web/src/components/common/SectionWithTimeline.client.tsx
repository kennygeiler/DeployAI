"use client";

import * as React from "react";

import { DateRangeFilter } from "@/components/common/DateRangeFilter.client";
import { DensityStrip } from "@/components/common/DensityStrip.client";
import { filterByRange, type Section, useTemporalFilter } from "@/lib/bff/temporal-filter";

type Props<T> = {
  name: Section;
  title: string;
  events: T[];
  getTimestamp: (e: T) => string;
  children: (filtered: T[]) => React.ReactNode;
  headingLevel?: "h2" | "h3";
};

export function SectionWithTimeline<T>({
  name,
  title,
  events,
  getTimestamp,
  children,
  headingLevel = "h2",
}: Props<T>) {
  const { range, setRange } = useTemporalFilter(name);

  const filtered = React.useMemo(
    () => filterByRange(events, getTimestamp, range),
    [events, getTimestamp, range],
  );

  const densityEvents = React.useMemo(
    () => events.map((e) => ({ timestamp: getTimestamp(e) })),
    [events, getTimestamp],
  );

  const HeadingTag = headingLevel;
  const headingId = `section-${name}-heading`;
  const totalShown = filtered.length;
  const totalAll = events.length;

  return (
    <section aria-labelledby={headingId} className="space-y-2">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <HeadingTag
          id={headingId}
          className={
            headingLevel === "h2"
              ? "text-ink-800 text-sm font-semibold"
              : "text-ink-700 text-xs font-semibold uppercase"
          }
        >
          {title}
          <span className="text-ink-500 ml-2 font-normal">
            {range.from || range.to ? `${totalShown} of ${totalAll}` : totalAll}
          </span>
        </HeadingTag>
        <DateRangeFilter
          value={range}
          onChange={setRange}
          label={`${title} date range`}
          idPrefix={`section-${name}`}
        />
      </div>
      <DensityStrip events={densityEvents} range={range} label={`${title} event density`} />
      {children(filtered)}
    </section>
  );
}
