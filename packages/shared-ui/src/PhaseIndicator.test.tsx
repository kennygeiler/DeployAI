import { afterEach } from "vitest";
import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { PhaseIndicator } from "./PhaseIndicator";

afterEach(cleanup);

describe("PhaseIndicator", () => {
  it("renders current phase label", () => {
    render(<PhaseIndicator currentPhaseId="P5_pilot" />);
    expect(screen.getByRole("button", { name: /Deployment phase: P5 Pilot/i })).toBeInTheDocument();
  });

  it("opens popover with stepper on click", async () => {
    const user = userEvent.setup();
    render(<PhaseIndicator currentPhaseId="P3_ecosystem_mapping" />);
    await user.click(
      screen.getByRole("button", { name: /Deployment phase: P3 Ecosystem mapping/i }),
    );
    await waitFor(() => {
      expect(screen.getByText("Deployment phase")).toBeInTheDocument();
    });
    const pop = screen.getByText("Deployment phase").closest('[data-slot="popover-content"]');
    expect(pop).toBeTruthy();
    if (pop) {
      expect(within(pop as HTMLElement).getByTestId("phase-stepper")).toBeInTheDocument();
    }
  });

  it("announces phase change in live region", async () => {
    const { rerender } = render(<PhaseIndicator currentPhaseId="P1_pre_engagement" />);
    rerender(<PhaseIndicator currentPhaseId="P2_discovery" />);
    await waitFor(() => {
      const live = document.querySelector("[aria-live='polite']");
      expect(live?.textContent).toMatch(/Now in Discovery/);
    });
  });

  it("renders locked state without a button", () => {
    render(<PhaseIndicator currentPhaseId="P4_design" variant="locked" />);
    expect(screen.queryByRole("button")).toBeNull();
    expect(document.querySelector("[data-phase-indicator='locked']")).toBeInTheDocument();
  });

  it("exposes pending-transition state on the trigger", () => {
    render(<PhaseIndicator currentPhaseId="P5_pilot" variant="pending-transition" />);
    expect(
      document.querySelector("button[data-phase-indicator='pending-transition']"),
    ).toBeInTheDocument();
  });
});
