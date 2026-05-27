import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import {
  AGENT_ACTIVITY_CHIP_SOURCE_KINDS,
  EXTERNAL_MCP_AUXILIARY_SOURCE_KINDS,
  EngagementTimelineFilters,
  resolveAgentActivitySourceKinds,
  type AgentActivityChip,
} from "@/components/engagements/EngagementTimelineFilters";
import {
  MCP_CONFIG_SOURCE_KINDS,
  MCP_KILLSWITCH_SOURCE_KIND,
  MCP_OUTBOUND_CALL_SOURCE_KINDS,
} from "@/lib/internal/ledger-cp";

describe("EngagementTimelineFilters", () => {
  it("renders the Agent activity chip group with all four chips", () => {
    render(<EngagementTimelineFilters selected={null} onChange={() => {}} />);
    const group = screen.getByTestId("agent-activity-chip-group");
    expect(group).toBeTruthy();
    expect(screen.getByTestId("agent-activity-chip-tool_calls_internal")).toBeTruthy();
    expect(screen.getByTestId("agent-activity-chip-external_mcp")).toBeTruthy();
    expect(screen.getByTestId("agent-activity-chip-synthesis")).toBeTruthy();
    expect(screen.getByTestId("agent-activity-chip-adversarial_concerns")).toBeTruthy();
  });

  it("reports the selected chip via aria-pressed", () => {
    render(<EngagementTimelineFilters selected="external_mcp" onChange={() => {}} />);
    const externalChip = screen.getByTestId("agent-activity-chip-external_mcp");
    expect(externalChip.getAttribute("aria-pressed")).toBe("true");
    const synthesisChip = screen.getByTestId("agent-activity-chip-synthesis");
    expect(synthesisChip.getAttribute("aria-pressed")).toBe("false");
  });

  it("invokes onChange with the chip on click, and null on click-to-clear", () => {
    const onChange = vi.fn<(c: AgentActivityChip | null) => void>();
    const { rerender } = render(<EngagementTimelineFilters selected={null} onChange={onChange} />);
    fireEvent.click(screen.getByTestId("agent-activity-chip-external_mcp"));
    expect(onChange).toHaveBeenCalledWith("external_mcp");

    rerender(<EngagementTimelineFilters selected="external_mcp" onChange={onChange} />);
    fireEvent.click(screen.getByTestId("agent-activity-chip-external_mcp"));
    expect(onChange).toHaveBeenLastCalledWith(null);
  });

  it('"External (MCP)" chip maps to the four outbound call source_kinds', () => {
    const kinds = AGENT_ACTIVITY_CHIP_SOURCE_KINDS.external_mcp;
    expect(kinds).toEqual([...MCP_OUTBOUND_CALL_SOURCE_KINDS]);
    expect(kinds).toContain("mcp_outbound_call");
    expect(kinds).toContain("mcp_outbound_blocked");
    expect(kinds).toContain("mcp_outbound_rate_limited");
    expect(kinds).toContain("mcp_outbound_denied");
  });

  it("resolveAgentActivitySourceKinds widens 'external_mcp' with auxiliary kinds when requested", () => {
    const base = resolveAgentActivitySourceKinds("external_mcp");
    expect(base).toEqual([...MCP_OUTBOUND_CALL_SOURCE_KINDS]);

    const wide = resolveAgentActivitySourceKinds("external_mcp", { includeMcpAuxiliary: true });
    for (const k of MCP_OUTBOUND_CALL_SOURCE_KINDS) expect(wide).toContain(k);
    for (const k of MCP_CONFIG_SOURCE_KINDS) expect(wide).toContain(k);
    expect(wide).toContain(MCP_KILLSWITCH_SOURCE_KIND);

    expect(EXTERNAL_MCP_AUXILIARY_SOURCE_KINDS).toContain(MCP_KILLSWITCH_SOURCE_KIND);
  });

  it("resolveAgentActivitySourceKinds returns [] for a null chip", () => {
    expect(resolveAgentActivitySourceKinds(null)).toEqual([]);
    expect(resolveAgentActivitySourceKinds(null, { includeMcpAuxiliary: true })).toEqual([]);
  });

  it("non-external chips never widen even with includeMcpAuxiliary=true", () => {
    const synthesis = resolveAgentActivitySourceKinds("synthesis", {
      includeMcpAuxiliary: true,
    });
    expect(synthesis).toEqual([...AGENT_ACTIVITY_CHIP_SOURCE_KINDS.synthesis]);
    expect(synthesis).not.toContain("mcp_outbound_call");
  });
});
