import { render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { TimestampLabel, formatRelative } from "@/components/common/TimestampLabel.client";

const NOW = new Date("2026-05-25T12:00:00.000Z");

describe("formatRelative", () => {
  it("returns 'just now' for under 60 seconds", () => {
    expect(formatRelative("2026-05-25T11:59:30.000Z", NOW)).toBe("just now");
  });

  it("returns minutes ago for under an hour", () => {
    expect(formatRelative("2026-05-25T11:45:00.000Z", NOW)).toBe("15m ago");
  });

  it("returns hours ago for under a day", () => {
    expect(formatRelative("2026-05-25T09:00:00.000Z", NOW)).toBe("3h ago");
  });

  it("returns days ago for under a week", () => {
    expect(formatRelative("2026-05-22T12:00:00.000Z", NOW)).toBe("3d ago");
  });

  it("returns 'Mon DD' for older dates in the current year", () => {
    expect(formatRelative("2026-02-14T08:00:00.000Z", NOW)).toBe("Feb 14");
  });

  it("returns 'Mon DD, YYYY' for dates in a different year", () => {
    expect(formatRelative("2024-11-03T08:00:00.000Z", NOW)).toBe("Nov 3, 2024");
  });

  it("returns the raw input string when value is unparseable", () => {
    expect(formatRelative("not-a-date", NOW)).toBe("not-a-date");
  });
});

describe("TimestampLabel", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(NOW);
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it("renders a semantic <time> element with the ISO dateTime attribute", () => {
    render(<TimestampLabel value="2026-05-22T12:00:00.000Z" />);
    const t = document.querySelector("time");
    expect(t).not.toBeNull();
    expect(t!.getAttribute("datetime")).toBe("2026-05-22T12:00:00.000Z");
    expect(t!.textContent).toBe("3d ago");
  });

  it("exposes the full ISO via the tooltip (title attribute on the time element)", () => {
    render(<TimestampLabel value="2026-05-22T12:00:00.000Z" />);
    const t = document.querySelector("time");
    expect(t?.getAttribute("title")).toBe("2026-05-22T12:00:00.000Z");
  });

  it("prefixes the visible label when prefix is supplied", () => {
    render(<TimestampLabel value="2026-05-25T11:30:00.000Z" prefix="created" />);
    expect(screen.getByText("created 30m ago")).toBeTruthy();
  });

  it("renders the fallback when the value is invalid, and does not crash", () => {
    render(<TimestampLabel value="garbage" fallback="unknown" prefix="created" />);
    expect(screen.getByText("created unknown")).toBeTruthy();
    expect(document.querySelector("time")).toBeNull();
  });

  it("renders the fallback when the value is null or empty", () => {
    const { rerender } = render(<TimestampLabel value={null} fallback="never" />);
    expect(screen.getByText("never")).toBeTruthy();
    rerender(<TimestampLabel value="" fallback="never" />);
    expect(screen.getByText("never")).toBeTruthy();
  });
});
