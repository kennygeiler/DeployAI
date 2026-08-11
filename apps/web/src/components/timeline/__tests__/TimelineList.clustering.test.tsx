import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { buildClusteredRows, TimelineList } from "@/components/timeline/TimelineList.client";
import type { LedgerEvent } from "@/lib/internal/ledger-cp";

function mkEvent(id: string, occurred_at: string, source_kind = "manual_capture"): LedgerEvent {
  return {
    id,
    engagement_id: "e1",
    occurred_at,
    recorded_at: occurred_at,
    actor_kind: "user",
    actor_id: null,
    source_kind,
    source_ref: null,
    summary: `Event ${id}`,
    detail: {},
    caused_by_ids: [],
    affects: [],
  } as unknown as LedgerEvent;
}

describe("buildClusteredRows (U8)", () => {
  it("clusters events under one header per day with counts", () => {
    const rows = buildClusteredRows([
      mkEvent("a", "2026-08-10T09:00:00Z"),
      mkEvent("b", "2026-08-10T15:00:00Z"),
      mkEvent("c", "2026-08-09T12:00:00Z"),
    ]);
    const headers = rows.filter((r) => r.type === "header");
    expect(headers).toHaveLength(2);
    expect(headers[0]!.count).toBe(2);
    expect(headers[1]!.count).toBe(1);
    expect(rows[0]!.type).toBe("header");
    expect(rows[1]!.type).toBe("event");
  });

  it("switches to week clustering at XL densities", () => {
    const events: LedgerEvent[] = [];
    // 200 events spread over ~40 days → day clustering would mean ~40 headers;
    // week clustering caps it near 7.
    for (let i = 0; i < 200; i++) {
      const day = String(1 + (i % 28)).padStart(2, "0");
      events.push(mkEvent(`e${i}`, `2026-07-${day}T10:00:00Z`));
    }
    events.sort((a, b) => (a.occurred_at < b.occurred_at ? 1 : -1));
    const rows = buildClusteredRows(events);
    const headers = rows.filter((r) => r.type === "header");
    expect(headers.length).toBeLessThanOrEqual(8);
    expect(headers[0]!.label).toMatch(/^Week of /);
  });
});

describe("TimelineList clustering render", () => {
  it("renders day headers with human kind labels and icons in rows", () => {
    render(
      <TimelineList
        events={[
          mkEvent("a", "2026-08-10T09:00:00Z", "email_ingest"),
          mkEvent("b", "2026-08-09T09:00:00Z", "risk_closed"),
        ]}
        onSelect={vi.fn()}
      />,
    );
    const headers = screen.getAllByTestId("timeline-day-header");
    expect(headers.length).toBe(2);
    // Human labels, not raw enums.
    expect(screen.getByTestId("timeline-row-a").textContent).toContain("Email imported");
    expect(screen.getByTestId("timeline-row-b").textContent).toContain("Risk closed");
  });
});
