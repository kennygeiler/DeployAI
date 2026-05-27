import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { McpTimelineRow } from "@/components/engagements/McpTimelineRow";
import type { LedgerEvent } from "@/lib/internal/ledger-cp";

type RowEvent = Pick<
  LedgerEvent,
  "id" | "occurred_at" | "source_kind" | "summary" | "detail" | "actor_id"
>;

function mkEvent(overrides: Partial<RowEvent> = {}): RowEvent {
  return {
    id: "evt-1",
    occurred_at: "2026-05-20T10:00:00Z",
    source_kind: "mcp_outbound_call",
    summary: "slack.search_messages ok",
    actor_id: "agent-kenny",
    detail: {
      connector_kind: "slack",
      tool: "slack.search_messages",
      latency_ms: 142,
    },
    ...overrides,
  };
}

describe("McpTimelineRow", () => {
  it("renders an mcp_outbound_call row with connector badge, tool, status, latency, and Outbound MCP tag", () => {
    render(<McpTimelineRow event={mkEvent()} />);

    const row = screen.getByTestId("mcp-timeline-row-evt-1");
    expect(row.getAttribute("data-mcp-kind")).toBe("mcp_outbound_call");

    const badge = screen.getByTestId("mcp-connector-badge-slack");
    expect(badge.textContent).toContain("Slack");

    expect(row.textContent).toContain("slack.search_messages");
    expect(row.textContent).toContain("Outbound MCP");

    const statusEl = screen.getByTestId("mcp-status-mcp_outbound_call");
    expect(statusEl.textContent?.toLowerCase()).toContain("ok");

    const latency = screen.getByTestId("mcp-latency");
    expect(latency.textContent).toContain("142");
    expect(latency.textContent).toContain("ms");
  });

  it("renders an mcp_outbound_blocked row with the blocked status badge", () => {
    render(
      <McpTimelineRow
        event={mkEvent({
          id: "evt-2",
          source_kind: "mcp_outbound_blocked",
          summary: "killswitch blocked",
          detail: { connector_kind: "linear", tool: "linear.list_issues" },
        })}
      />,
    );
    const row = screen.getByTestId("mcp-timeline-row-evt-2");
    expect(row.getAttribute("data-mcp-kind")).toBe("mcp_outbound_blocked");
    expect(screen.getByTestId("mcp-connector-badge-linear")).toBeTruthy();
    const statusEl = screen.getByTestId("mcp-status-mcp_outbound_blocked");
    expect(statusEl.textContent?.toLowerCase()).toContain("blocked");
  });

  it("renders an mcp_config_* row with the Config change tag and connector label", () => {
    render(
      <McpTimelineRow
        event={mkEvent({
          id: "evt-3",
          source_kind: "mcp_config_updated",
          summary: "allowed_tools updated",
          detail: { connector_kind: "github" },
        })}
      />,
    );
    const row = screen.getByTestId("mcp-timeline-row-evt-3");
    expect(row.getAttribute("data-mcp-kind")).toBe("mcp_config_updated");
    expect(row.textContent).toContain("Config change");
    expect(row.textContent).toContain("GitHub");
    expect(row.textContent).toContain("updated");
  });

  it("renders the kill-switch row with a Kill switch tag and the boolean state", () => {
    render(
      <McpTimelineRow
        event={mkEvent({
          id: "evt-4",
          source_kind: "mcp_outbound_killswitch_changed",
          summary: "Kill switch flipped",
          actor_id: "on-call-sre",
          detail: { disabled: true },
        })}
      />,
    );
    const row = screen.getByTestId("mcp-timeline-row-evt-4");
    expect(row.getAttribute("data-mcp-kind")).toBe("mcp_outbound_killswitch_changed");
    expect(row.textContent).toContain("Kill switch");
    expect(row.textContent).toContain("disabled");
    expect(row.textContent).toContain("on-call-sre");
  });

  it("falls back to summary when an outbound row lacks tool/connector detail", () => {
    render(
      <McpTimelineRow
        event={mkEvent({
          id: "evt-5",
          source_kind: "mcp_outbound_denied",
          summary: "tool not in allow-list",
          detail: {},
        })}
      />,
    );
    const row = screen.getByTestId("mcp-timeline-row-evt-5");
    expect(row.textContent).toContain("unknown tool");
    expect(row.textContent).toContain("denied");
    expect(row.textContent).toContain("tool not in allow-list");
  });
});
