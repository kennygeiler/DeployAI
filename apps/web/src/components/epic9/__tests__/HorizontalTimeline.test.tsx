import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeAll, describe, expect, it, vi } from "vitest";

import { HorizontalTimeline, type HorizontalTimelineEvent } from "../HorizontalTimeline.client";

beforeAll(() => {
  class RO {
    observe() {}
    unobserve() {}
    disconnect() {}
  }
  vi.stubGlobal("ResizeObserver", RO);
});

function mkEvent(overrides: Partial<HorizontalTimelineEvent> = {}): HorizontalTimelineEvent {
  return {
    id: "evt-1",
    occurred_at: "2026-05-20T10:00:00Z",
    source_kind: "email_ingest",
    summary: "Test event",
    actor_kind: "user",
    ...overrides,
  };
}

describe("HorizontalTimeline", () => {
  it("renders one interactive circle per event", () => {
    const events = [
      mkEvent({ id: "a", occurred_at: "2026-05-10T10:00:00Z" }),
      mkEvent({ id: "b", occurred_at: "2026-05-15T10:00:00Z" }),
      mkEvent({ id: "c", occurred_at: "2026-05-20T10:00:00Z" }),
    ];
    render(<HorizontalTimeline events={events} />);
    expect(screen.getByTestId("horizontal-timeline-event-a")).toBeTruthy();
    expect(screen.getByTestId("horizontal-timeline-event-b")).toBeTruthy();
    expect(screen.getByTestId("horizontal-timeline-event-c")).toBeTruthy();
  });

  it("shows the empty-state message when no events", () => {
    render(<HorizontalTimeline events={[]} />);
    expect(screen.getByTestId("horizontal-timeline-empty")).toBeTruthy();
    expect(screen.getByText(/No events in this range/)).toBeTruthy();
  });

  it("invokes onSelect with the event id when a circle is clicked", () => {
    const onSelect = vi.fn();
    const events = [mkEvent({ id: "click-target" })];
    render(<HorizontalTimeline events={events} onSelect={onSelect} />);
    const circle = screen.getByTestId("horizontal-timeline-event-click-target");
    fireEvent.click(circle);
    expect(onSelect).toHaveBeenCalledTimes(1);
    expect(onSelect).toHaveBeenCalledWith("click-target");
  });

  it("invokes onSelect when Enter is pressed on a focused circle", () => {
    const onSelect = vi.fn();
    const events = [mkEvent({ id: "kbd-target" })];
    render(<HorizontalTimeline events={events} onSelect={onSelect} />);
    const circle = screen.getByTestId("horizontal-timeline-event-kbd-target");
    fireEvent.keyDown(circle, { key: "Enter" });
    expect(onSelect).toHaveBeenCalledWith("kbd-target");
  });

  it("invokes onSelect when Space is pressed on a focused circle", () => {
    const onSelect = vi.fn();
    const events = [mkEvent({ id: "space-target" })];
    render(<HorizontalTimeline events={events} onSelect={onSelect} />);
    const circle = screen.getByTestId("horizontal-timeline-event-space-target");
    fireEvent.keyDown(circle, { key: " " });
    expect(onSelect).toHaveBeenCalledWith("space-target");
  });

  it("populates the info card above the chart on hover", () => {
    const events = [
      mkEvent({
        id: "hover-target",
        summary: "Hovered event summary",
        source_kind: "manual_capture",
      }),
    ];
    render(<HorizontalTimeline events={events} />);
    const card = screen.getByTestId("horizontal-timeline-info-card");
    // Placeholder copy before any hover.
    expect(card.textContent).toMatch(/Hover or focus an event/);
    const circle = screen.getByTestId("horizontal-timeline-event-hover-target");
    fireEvent.mouseEnter(circle);
    expect(card.textContent).toMatch(/Hovered event summary/);
    expect(card.textContent).toMatch(/manual_capture/);
  });

  it("zooms the SVG via the +/Reset/- button group", () => {
    const events = [
      mkEvent({ id: "z1" }),
      mkEvent({ id: "z2", occurred_at: "2026-02-01T00:00:00Z" }),
    ];
    render(<HorizontalTimeline events={events} />);
    const svg = screen.getByRole("img", { name: /Engagement timeline horizontal view/i });
    const baseWidth = Number(svg.getAttribute("width") ?? 0);
    expect(baseWidth).toBeGreaterThan(0);
    fireEvent.click(screen.getByTestId("horizontal-timeline-zoom-in"));
    fireEvent.click(screen.getByTestId("horizontal-timeline-zoom-in"));
    const zoomedInWidth = Number(svg.getAttribute("width") ?? 0);
    expect(zoomedInWidth).toBeGreaterThan(baseWidth);
    // Zoom out from the zoomed-in state — should drop below the prior width.
    fireEvent.click(screen.getByTestId("horizontal-timeline-zoom-out"));
    expect(Number(svg.getAttribute("width") ?? 0)).toBeLessThan(zoomedInWidth);
    // Reset returns to baseline.
    fireEvent.click(screen.getByTestId("horizontal-timeline-zoom-reset"));
    expect(Number(svg.getAttribute("width") ?? 0)).toBe(baseWidth);
  });

  it("renders a focused pulse ring when focusedEventId matches", async () => {
    const events = [mkEvent({ id: "focused" })];
    render(<HorizontalTimeline events={events} focusedEventId="focused" />);
    await waitFor(() => {
      expect(screen.getByTestId("horizontal-timeline-pulse-focused")).toBeTruthy();
    });
  });

  it("provides accessible labels on each event circle", () => {
    const events = [
      mkEvent({
        id: "a11y",
        source_kind: "matrix_node_created",
        summary: "A very informative summary",
        occurred_at: "2026-05-20T10:00:00Z",
      }),
    ];
    render(<HorizontalTimeline events={events} />);
    const circle = screen.getByTestId("horizontal-timeline-event-a11y");
    const aria = circle.getAttribute("aria-label") ?? "";
    expect(aria).toMatch(/matrix_node_created/);
    expect(aria).toMatch(/2026-05-20T10:00:00Z/);
    expect(aria).toMatch(/A very informative summary/);
    expect(circle.getAttribute("tabindex")).toBe("0");
  });

  it("renders an overflow indicator when more than 6 events share a day", () => {
    const day = "2026-05-20";
    const events = Array.from({ length: 9 }).map((_, i) =>
      mkEvent({ id: `e${i}`, occurred_at: `${day}T${String(10 + i).padStart(2, "0")}:00:00Z` }),
    );
    render(<HorizontalTimeline events={events} />);
    const overflow = screen.getByTestId("horizontal-timeline-overflow-0");
    expect(overflow.textContent).toBe("+3");
  });

  it("renders an SVG with role=img and a descriptive aria-label", () => {
    render(<HorizontalTimeline events={[mkEvent()]} />);
    const svg = document.querySelector('svg[role="img"]');
    expect(svg).toBeTruthy();
    expect(svg?.getAttribute("aria-label")).toMatch(/Engagement timeline/);
  });
});
