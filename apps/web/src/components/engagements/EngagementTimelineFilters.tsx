"use client";

import * as React from "react";

import { Button } from "@/components/ui/button";
import {
  MCP_CONFIG_SOURCE_KINDS,
  MCP_KILLSWITCH_SOURCE_KIND,
  MCP_OUTBOUND_CALL_SOURCE_KINDS,
} from "@/lib/internal/ledger-cp";

/**
 * Wave 3I — "Agent activity" filter chip group for the engagement timeline.
 *
 * Lets the strategist narrow the existing timeline to a slice of Kenny's
 * activity. Each chip maps to a set of ledger source_kinds; the parent
 * surface (e.g. ``EngagementTimeline.client.tsx``) owns the URL/query
 * state and decides which chip's source_kind set to push into the ledger
 * fetch.
 *
 * Chip semantics:
 *   - "Tool calls (internal)" — Kenny's first-party tool layer (Phase 1).
 *     Maps to ``tool_call`` once that source_kind is wired in (Wave 3G);
 *     for now this chip is a placeholder that filters to the agent actor.
 *   - "External (MCP)" — Wave 2D outbound MCP runtime. Four call-status
 *     kinds: ``mcp_outbound_call | mcp_outbound_blocked |
 *     mcp_outbound_rate_limited | mcp_outbound_denied``.
 *   - "Synthesis" — Phase 0.5 compounding synthesis layer outputs
 *     (insight_opened, recommendation_emitted).
 *   - "Adversarial concerns" — Phase 2 audit/critique kinds raised by
 *     the adversarial reviewer (agent_audit_concern,
 *     agent_concern_logged, agent_hallucination_unresolved).
 *
 * The chip set is intentionally short: the granular per-source-kind chips
 * stay in the existing source-kind filter rail on the timeline. This
 * group is the "what was the AI doing" lens the user asked for in
 * scope-v2.md §9 + threat-model §5.4.
 */

export type AgentActivityChip =
  | "tool_calls_internal"
  | "external_mcp"
  | "synthesis"
  | "adversarial_concerns";

const CHIP_LABELS: Record<AgentActivityChip, string> = {
  tool_calls_internal: "Tool calls (internal)",
  external_mcp: "External (MCP)",
  synthesis: "Synthesis",
  adversarial_concerns: "Adversarial concerns",
};

/** Source-kind set selected by each chip. */
export const AGENT_ACTIVITY_CHIP_SOURCE_KINDS: Record<AgentActivityChip, readonly string[]> = {
  // Wave 3G will emit a dedicated ``tool_call`` kind; until then the
  // chip narrows to the agent's other observable kinds so the chip
  // doesn't render empty. Documented in the component header.
  tool_calls_internal: ["llm_proposal_created", "proposal_accepted", "proposal_rejected"],
  external_mcp: [...MCP_OUTBOUND_CALL_SOURCE_KINDS],
  synthesis: ["insight_opened", "recommendation_emitted"],
  adversarial_concerns: [
    // Match the v2 Phase 2/3 ALLOWED_SOURCE_KINDS additions in
    // ``services/control-plane/src/control_plane/ledger/emitter.py``.
    "agent_audit_concern",
    "agent_concern_logged",
    "agent_hallucination_unresolved",
    "agent_cross_engagement_leak",
  ],
};

/** Auxiliary MCP source kinds the "External (MCP)" chip *also* surfaces
 * because they're informational about the same external integration —
 * the user wants to see "Slack was configured" right next to the calls
 * that ran. The timeline row renderer tags these distinctly.
 */
export const EXTERNAL_MCP_AUXILIARY_SOURCE_KINDS: readonly string[] = [
  ...MCP_CONFIG_SOURCE_KINDS,
  MCP_KILLSWITCH_SOURCE_KIND,
];

const ALL_CHIPS: readonly AgentActivityChip[] = [
  "tool_calls_internal",
  "external_mcp",
  "synthesis",
  "adversarial_concerns",
];

export type EngagementTimelineFiltersProps = {
  selected: AgentActivityChip | null;
  onChange: (chip: AgentActivityChip | null) => void;
  /**
   * When true, the "External (MCP)" chip's source-kind set is widened to
   * also include config-change + killswitch kinds. The custom row
   * renderer tags those with their own label so they don't get confused
   * with actual outbound calls.
   */
  includeMcpAuxiliary?: boolean;
};

/**
 * Resolve the source_kinds that should be sent to the ledger fetch for
 * a given chip + include-auxiliary preference. Shared with the parent
 * surface and the unit test so both stay aligned with the chip
 * semantics in this module.
 */
export function resolveAgentActivitySourceKinds(
  chip: AgentActivityChip | null,
  opts: { includeMcpAuxiliary?: boolean } = {},
): string[] {
  if (chip === null) return [];
  const base = AGENT_ACTIVITY_CHIP_SOURCE_KINDS[chip];
  if (chip === "external_mcp" && opts.includeMcpAuxiliary) {
    return [...base, ...EXTERNAL_MCP_AUXILIARY_SOURCE_KINDS];
  }
  return [...base];
}

export function EngagementTimelineFilters({
  selected,
  onChange,
  includeMcpAuxiliary = true,
}: EngagementTimelineFiltersProps): React.ReactElement {
  void includeMcpAuxiliary; // parent uses it when resolving source_kinds
  return (
    <div
      role="group"
      aria-label="Agent activity filter"
      data-testid="agent-activity-chip-group"
      className="flex flex-wrap items-center gap-1"
    >
      <span className="text-ink-600 mr-1 text-xs font-medium">Agent activity:</span>
      {ALL_CHIPS.map((chip) => {
        const active = selected === chip;
        return (
          <Button
            key={chip}
            type="button"
            variant={active ? "default" : "outline"}
            size="xs"
            aria-pressed={active}
            data-testid={`agent-activity-chip-${chip}`}
            onClick={() => onChange(active ? null : chip)}
          >
            {CHIP_LABELS[chip]}
          </Button>
        );
      })}
    </div>
  );
}
