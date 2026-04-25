import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { InMeetingAlertCard } from "./InMeetingAlertCard";

const base = {
  tenantId: "t-1",
  meetingTitle: "Meeting with GC",
  phaseLabel: "P5 Pilot",
  freshnessLabel: "synced 6s ago",
  positionStorageKey: "test-in-meeting-alert-pos",
};

describe("InMeetingAlertCard", () => {
  it("exposes complementary landmark with required label", () => {
    render(
      <InMeetingAlertCard {...base} state="active">
        <span>chip</span>
      </InMeetingAlertCard>,
    );
    expect(screen.getByRole("complementary", { name: "In-meeting alert" })).toBeInTheDocument();
  });

  it("renders nothing when archived", () => {
    const { container } = render(
      <InMeetingAlertCard {...base} state="archived">
        <span>chip</span>
      </InMeetingAlertCard>,
    );
    expect(container.firstChild).toBeNull();
  });
});
