"use client";

import { ChevronDownIcon } from "lucide-react";
import * as React from "react";

import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import {
  BUILTIN_TYPE_BG,
  BUILTIN_TYPE_COLOR_NAME,
  BUILTIN_TYPE_LABEL,
  BUILTIN_TYPE_ORDER,
  EDGE_STYLE,
} from "@/components/epic9/MatrixGraph.client";

function humanizeEdgeType(t: string): string {
  return t.replace(/_/g, " ");
}

export function MatrixLegend() {
  const [open, setOpen] = React.useState(false);
  const contentId = React.useId();
  const edgeEntries = Object.entries(EDGE_STYLE);
  return (
    <Collapsible
      open={open}
      onOpenChange={setOpen}
      data-testid="matrix-legend"
      className="border-border rounded-lg border"
    >
      <CollapsibleTrigger
        aria-controls={contentId}
        className="hover:bg-ink-50 flex w-full items-center justify-between gap-3 px-3 py-2 text-left"
      >
        <span className="text-ink-900 text-sm font-medium">Legend</span>
        <ChevronDownIcon
          aria-hidden="true"
          className={
            "text-ink-600 size-4 transition-transform duration-200 " +
            (open ? "rotate-180" : "rotate-0")
          }
        />
      </CollapsibleTrigger>
      <CollapsibleContent id={contentId}>
        <div className="space-y-3 border-t px-3 py-2 text-xs">
          <section aria-labelledby={`${contentId}-edges`}>
            <h3
              id={`${contentId}-edges`}
              className="text-ink-700 mb-1 text-[11px] font-semibold uppercase"
            >
              Edge types
            </h3>
            <ul
              data-testid="matrix-legend-edges"
              className="grid grid-cols-2 gap-x-3 gap-y-1 sm:grid-cols-3"
            >
              {edgeEntries.map(([type, style]) => (
                <li key={type} className="flex items-center gap-2">
                  <svg
                    aria-hidden="true"
                    width="24"
                    height="10"
                    viewBox="0 0 24 10"
                    className="shrink-0"
                  >
                    <line
                      x1="0"
                      y1="5"
                      x2="24"
                      y2="5"
                      stroke={style.stroke}
                      strokeWidth="2"
                      strokeDasharray={style.strokeDasharray}
                    />
                  </svg>
                  <span className="text-ink-900">{humanizeEdgeType(type)}</span>
                  <span className="sr-only">color {style.colorName}</span>
                </li>
              ))}
            </ul>
          </section>
          <section aria-labelledby={`${contentId}-nodes`}>
            <h3
              id={`${contentId}-nodes`}
              className="text-ink-700 mb-1 text-[11px] font-semibold uppercase"
            >
              Node types
            </h3>
            <ul data-testid="matrix-legend-nodes" className="flex flex-wrap gap-1.5">
              {BUILTIN_TYPE_ORDER.map((type) => (
                <li
                  key={type}
                  className="border-border flex items-center gap-1.5 rounded-full border px-2 py-0.5"
                  style={{ background: BUILTIN_TYPE_BG[type] }}
                >
                  <span className="text-ink-900">{BUILTIN_TYPE_LABEL[type]}</span>
                  <span className="sr-only">color {BUILTIN_TYPE_COLOR_NAME[type]}</span>
                </li>
              ))}
            </ul>
          </section>
        </div>
      </CollapsibleContent>
    </Collapsible>
  );
}
