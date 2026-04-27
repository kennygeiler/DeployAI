import { fireEvent, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
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

  it("header context menu offers reset when showResetPosition (Story 9.8)", async () => {
    const user = userEvent.setup();
    render(
      <InMeetingAlertCard {...base} state="active" showResetPosition userId="u-1">
        <span>chip</span>
      </InMeetingAlertCard>,
    );
    const landmark = screen.getByRole("complementary", { name: "In-meeting alert" });
    const title = within(landmark).getByText("Meeting with GC");
    const header = title.closest('[role="presentation"]');
    expect(header).toBeTruthy();
    fireEvent.contextMenu(header!);
    const item = await screen.findByRole("menuitem", { name: /reset position to default/i });
    await user.click(item);
  });
});
