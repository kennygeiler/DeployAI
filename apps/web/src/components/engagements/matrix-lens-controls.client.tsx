"use client";

import * as React from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import type { MatrixNode } from "@/lib/bff/matrix-types";

/**
 * Wave 2.5 ticket U5 — controls for the MatrixGraph lens view: a type-ahead
 * search over node titles (grouped by node type) that re-focuses the lens,
 * and node-type filter chips with per-type count badges that work in both
 * lens and full-graph modes.
 */

const MAX_SEARCH_RESULTS = 20;

type SearchGroup = { type: string; label: string; nodes: MatrixNode[] };

function groupMatches(
  nodes: MatrixNode[],
  query: string,
  typeOrder: string[],
  labelMap: Map<string, string>,
): SearchGroup[] {
  const q = query.trim().toLowerCase();
  if (q.length === 0) return [];
  const matches: MatrixNode[] = [];
  for (const n of nodes) {
    if (n.title.toLowerCase().includes(q)) {
      matches.push(n);
      if (matches.length >= MAX_SEARCH_RESULTS) break;
    }
  }
  const rank = new Map(typeOrder.map((t, i) => [t, i]));
  const byType = new Map<string, MatrixNode[]>();
  for (const n of matches) {
    const list = byType.get(n.node_type) ?? [];
    list.push(n);
    byType.set(n.node_type, list);
  }
  return [...byType.entries()]
    .sort(
      ([a], [b]) =>
        (rank.get(a) ?? Number.MAX_SAFE_INTEGER) - (rank.get(b) ?? Number.MAX_SAFE_INTEGER),
    )
    .map(([type, groupNodes]) => ({
      type,
      label: labelMap.get(type) ?? type,
      nodes: groupNodes,
    }));
}

export function MatrixNodeSearch({
  nodes,
  typeOrder,
  labelMap,
  onSelect,
}: {
  nodes: MatrixNode[];
  typeOrder: string[];
  labelMap: Map<string, string>;
  onSelect: (node: MatrixNode) => void;
}) {
  const [query, setQuery] = React.useState("");
  const [open, setOpen] = React.useState(false);
  const [activeIndex, setActiveIndex] = React.useState(0);
  const listboxId = React.useId();

  const groups = React.useMemo(
    () => groupMatches(nodes, query, typeOrder, labelMap),
    [nodes, query, typeOrder, labelMap],
  );
  const flat = React.useMemo(() => groups.flatMap((g) => g.nodes), [groups]);
  const clampedActive = Math.min(activeIndex, Math.max(0, flat.length - 1));

  const select = React.useCallback(
    (node: MatrixNode) => {
      onSelect(node);
      setQuery("");
      setOpen(false);
      setActiveIndex(0);
    },
    [onSelect],
  );

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setActiveIndex((i) => Math.min(i + 1, Math.max(0, flat.length - 1)));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActiveIndex((i) => Math.max(i - 1, 0));
    } else if (e.key === "Enter") {
      const node = flat[clampedActive];
      if (open && node) {
        e.preventDefault();
        select(node);
      }
    } else if (e.key === "Escape") {
      setOpen(false);
    }
  };

  const showList = open && query.trim().length > 0;
  let optionIndex = -1;

  return (
    <div className="relative min-w-[14rem] flex-1" data-testid="matrix-lens-search">
      <Input
        role="combobox"
        aria-expanded={showList}
        aria-controls={listboxId}
        aria-autocomplete="list"
        aria-activedescendant={
          showList && flat.length > 0 ? `${listboxId}-opt-${clampedActive}` : undefined
        }
        aria-label="Search matrix nodes"
        placeholder="Search nodes to focus…"
        value={query}
        onChange={(e) => {
          setQuery(e.target.value);
          setOpen(true);
          setActiveIndex(0);
        }}
        onFocus={() => setOpen(true)}
        onKeyDown={handleKeyDown}
        onBlur={() => {
          // Delay so option mousedown/click can land before the list closes.
          window.setTimeout(() => setOpen(false), 150);
        }}
        className="h-8 text-xs"
      />
      {showList ? (
        <ul
          id={listboxId}
          role="listbox"
          aria-label="Matching nodes"
          data-testid="matrix-lens-search-results"
          className="border-border bg-paper-50 absolute z-20 mt-1 max-h-72 w-full overflow-auto rounded-lg border p-1 shadow-md"
        >
          {flat.length === 0 ? (
            <li role="presentation" className="text-ink-500 px-2 py-1.5 text-xs">
              No nodes match “{query.trim()}”.
            </li>
          ) : (
            groups.map((group) => (
              <li key={group.type} role="group" aria-label={group.label}>
                <span className="text-ink-500 block px-2 pt-1.5 pb-0.5 text-[10px] font-semibold uppercase">
                  {group.label}
                </span>
                <ul role="presentation">
                  {group.nodes.map((node) => {
                    optionIndex += 1;
                    const isActive = optionIndex === clampedActive;
                    return (
                      <li
                        key={node.id}
                        id={`${listboxId}-opt-${optionIndex}`}
                        role="option"
                        aria-selected={isActive}
                        className={
                          "cursor-pointer rounded px-2 py-1.5 text-xs " +
                          (isActive ? "bg-ink-100 text-ink-900" : "text-ink-800 hover:bg-ink-50")
                        }
                        onMouseDown={(e) => {
                          // Select on mousedown so the input blur doesn't
                          // unmount the option before click fires.
                          e.preventDefault();
                          select(node);
                        }}
                      >
                        {node.title}
                      </li>
                    );
                  })}
                </ul>
              </li>
            ))
          )}
        </ul>
      ) : null}
    </div>
  );
}

export function MatrixTypeFilterChips({
  typeOrder,
  counts,
  labelMap,
  bgMap,
  hiddenTypes,
  onToggle,
}: {
  typeOrder: string[];
  counts: Map<string, number>;
  labelMap: Map<string, string>;
  bgMap: Map<string, string>;
  hiddenTypes: ReadonlySet<string>;
  onToggle: (type: string) => void;
}) {
  const presentTypes = typeOrder.filter((t) => (counts.get(t) ?? 0) > 0);
  if (presentTypes.length === 0) return null;
  return (
    <div
      className="flex flex-wrap items-center gap-1.5"
      role="group"
      aria-label="Filter by node type"
      data-testid="matrix-type-filters"
    >
      {presentTypes.map((type) => {
        const enabled = !hiddenTypes.has(type);
        const label = labelMap.get(type) ?? type;
        return (
          <Button
            key={type}
            type="button"
            variant="ghost"
            size="xs"
            aria-pressed={enabled}
            data-testid={`matrix-type-filter-${type}`}
            onClick={() => onToggle(type)}
            className={
              "border-border gap-1.5 border font-normal " +
              (enabled ? "bg-paper-50 text-ink-800" : "text-ink-400 bg-transparent line-through")
            }
          >
            <span
              aria-hidden="true"
              className="size-2.5 rounded-full border border-black/20"
              style={{ background: bgMap.get(type) ?? "#e5e7eb" }}
            />
            {label}
            <span
              className={
                "rounded-full px-1 font-mono text-[10px] " +
                (enabled ? "bg-ink-100 text-ink-700" : "bg-transparent")
              }
              data-testid={`matrix-type-count-${type}`}
            >
              {counts.get(type) ?? 0}
            </span>
          </Button>
        );
      })}
    </div>
  );
}
