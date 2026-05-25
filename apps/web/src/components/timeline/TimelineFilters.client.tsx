"use client";

import * as React from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

export type TimelineFilterValue = {
  sourceKinds: string[];
  actorId: string;
  from: string;
  to: string;
};

export const SOURCE_KIND_OPTIONS: ReadonlyArray<{ value: string; label: string }> = [
  { value: "email_ingest", label: "Email ingest" },
  { value: "meeting_webhook", label: "Meeting webhook" },
  { value: "manual_capture", label: "Manual capture" },
  { value: "llm_proposal_created", label: "LLM proposal" },
  { value: "proposal_accepted", label: "Proposal accepted" },
  { value: "proposal_rejected", label: "Proposal rejected" },
  { value: "matrix_node_created", label: "Node created" },
  { value: "matrix_node_updated", label: "Node updated" },
  { value: "matrix_node_deleted", label: "Node deleted" },
  { value: "matrix_edge_created", label: "Edge created" },
  { value: "matrix_edge_deleted", label: "Edge deleted" },
  { value: "insight_opened", label: "Insight opened" },
  { value: "insight_closed", label: "Insight closed" },
  { value: "recommendation_emitted", label: "Recommendation emitted" },
  { value: "recommendation_actioned", label: "Recommendation actioned" },
  { value: "engagement_phase_change", label: "Phase change" },
  { value: "member_added", label: "Member added" },
  { value: "member_removed", label: "Member removed" },
  { value: "settings_change", label: "Settings change" },
  { value: "audit_other", label: "Audit (other)" },
];

export function TimelineFilters({
  value,
  onChange,
}: {
  value: TimelineFilterValue;
  onChange: (next: TimelineFilterValue) => void;
}) {
  const toggleKind = (kind: string) => {
    const set = new Set(value.sourceKinds);
    if (set.has(kind)) {
      set.delete(kind);
    } else {
      set.add(kind);
    }
    onChange({ ...value, sourceKinds: Array.from(set) });
  };

  const clearAll = () => {
    onChange({ sourceKinds: [], actorId: "", from: "", to: "" });
  };

  return (
    <aside
      aria-label="Timeline filters"
      className="border-border bg-background w-64 shrink-0 space-y-5 rounded-lg border p-4 text-sm"
    >
      <div className="flex items-center justify-between">
        <h2 className="text-ink-800 text-sm font-semibold">Filters</h2>
        <Button variant="ghost" size="sm" onClick={clearAll} aria-label="Clear all filters">
          Clear
        </Button>
      </div>

      <fieldset className="space-y-2">
        <legend className="text-ink-700 text-xs font-semibold uppercase">Source</legend>
        <ul className="max-h-64 space-y-1 overflow-y-auto">
          {SOURCE_KIND_OPTIONS.map((opt) => {
            const checked = value.sourceKinds.includes(opt.value);
            return (
              <li key={opt.value}>
                <label className="text-ink-700 flex cursor-pointer items-center gap-2">
                  <input
                    type="checkbox"
                    checked={checked}
                    onChange={() => toggleKind(opt.value)}
                    aria-label={opt.label}
                  />
                  <span>{opt.label}</span>
                </label>
              </li>
            );
          })}
        </ul>
      </fieldset>

      <div className="space-y-1">
        <Label htmlFor="timeline-actor">Actor</Label>
        <Input
          id="timeline-actor"
          type="text"
          placeholder="user id or agent name"
          value={value.actorId}
          onChange={(e) => onChange({ ...value, actorId: e.target.value })}
        />
      </div>

      <div className="space-y-2">
        <div className="space-y-1">
          <Label htmlFor="timeline-from">From</Label>
          <Input
            id="timeline-from"
            type="datetime-local"
            value={value.from}
            onChange={(e) => onChange({ ...value, from: e.target.value })}
          />
        </div>
        <div className="space-y-1">
          <Label htmlFor="timeline-to">To</Label>
          <Input
            id="timeline-to"
            type="datetime-local"
            value={value.to}
            onChange={(e) => onChange({ ...value, to: e.target.value })}
          />
        </div>
      </div>
    </aside>
  );
}
