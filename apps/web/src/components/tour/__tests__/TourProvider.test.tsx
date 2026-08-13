import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { TourProvider } from "@/components/tour/TourProvider.client";
import {
  TOUR_CAPTURE_DONE_EVENT,
  TOUR_CAPTURE_PREFILL_EVENT,
  TOUR_CHAT_OPENED_EVENT,
  TOUR_DISMISSED_KEY,
  TOUR_PREFILL_EVENT,
  TOUR_STEP_KEY,
  TOUR_STEPS,
} from "@/lib/tour/steps";

let mockPathname = "/engagements";
vi.mock("next/navigation", () => ({
  usePathname: () => mockPathname,
}));

function setTourCookie(on: boolean) {
  document.cookie = on ? "demo_tour=1; path=/" : "demo_tour=; path=/; max-age=0";
}

function stepIndexOf(id: string): number {
  const i = TOUR_STEPS.findIndex((s) => s.id === id);
  if (i === -1) throw new Error(`unknown step id ${id}`);
  return i;
}

describe("TourProvider", () => {
  beforeEach(() => {
    mockPathname = "/engagements";
    window.sessionStorage.clear();
    setTourCookie(true);
  });

  afterEach(() => {
    setTourCookie(false);
    window.sessionStorage.clear();
  });

  it("renders nothing without the demo_tour cookie", () => {
    setTourCookie(false);
    render(<TourProvider />);
    expect(screen.queryByTestId("demo-tour-popover")).toBeNull();
  });

  it("mounts on the cookie and shows step 1", async () => {
    render(<TourProvider />);
    const popover = await screen.findByTestId("demo-tour-popover");
    expect(popover.getAttribute("data-tour-step")).toBe("portfolio-open-deal");
    expect(popover.getAttribute("role")).toBe("dialog");
    expect(screen.getByText("Your portfolio")).toBeTruthy();
  });

  it("renders nothing when dismissed in this session", () => {
    window.sessionStorage.setItem(TOUR_DISMISSED_KEY, "1");
    render(<TourProvider />);
    expect(screen.queryByTestId("demo-tour-popover")).toBeNull();
  });

  it("resumes from the sessionStorage step index", async () => {
    window.sessionStorage.setItem(TOUR_STEP_KEY, String(stepIndexOf("brief-needs-you")));
    render(<TourProvider />);
    const popover = await screen.findByTestId("demo-tour-popover");
    expect(popover.getAttribute("data-tour-step")).toBe("brief-needs-you");
  });

  it("advances on a route match (deal opened)", async () => {
    const { rerender } = render(<TourProvider />);
    await screen.findByTestId("demo-tour-popover");
    mockPathname = "/engagements/deal-123";
    rerender(<TourProvider />);
    await waitFor(() =>
      expect(screen.getByTestId("demo-tour-popover").getAttribute("data-tour-step")).toBe(
        "brief-delta",
      ),
    );
  });

  it("advances when the target of a click-target step is clicked", async () => {
    window.sessionStorage.setItem(TOUR_STEP_KEY, String(stepIndexOf("click-citation")));
    const user = userEvent.setup();
    render(
      <div>
        <ul data-tour="oracle-citations">
          <li>decision:abc12345</li>
        </ul>
        <TourProvider />
      </div>,
    );
    await screen.findByTestId("demo-tour-popover");
    await user.click(screen.getByText("decision:abc12345"));
    await waitFor(() =>
      expect(screen.getByTestId("demo-tour-popover").getAttribute("data-tour-step")).toBe(
        "the-trap",
      ),
    );
  });

  it("advances on the chat-opened custom event and shows the thinking step", async () => {
    window.sessionStorage.setItem(TOUR_STEP_KEY, String(stepIndexOf("ask-kenny")));
    render(<TourProvider />);
    await screen.findByTestId("demo-tour-popover");
    act(() => {
      window.dispatchEvent(new CustomEvent(TOUR_CHAT_OPENED_EVENT));
    });
    await waitFor(() =>
      expect(screen.getByTestId("demo-tour-popover").getAttribute("data-tour-step")).toBe(
        "watch-it-think",
      ),
    );
    // Persisted so a reload resumes here.
    expect(window.sessionStorage.getItem(TOUR_STEP_KEY)).toBe(
      String(stepIndexOf("watch-it-think")),
    );
  });

  it('dispatches the prefill event from "Use this question"', async () => {
    window.sessionStorage.setItem(TOUR_STEP_KEY, String(stepIndexOf("ask-kenny")));
    const user = userEvent.setup();
    const seen: string[] = [];
    const onPrefill = (e: Event) => {
      seen.push(String((e as CustomEvent<{ question?: string }>).detail?.question));
    };
    window.addEventListener(TOUR_PREFILL_EVENT, onPrefill);
    try {
      render(<TourProvider />);
      await user.click(await screen.findByTestId("demo-tour-prefill"));
      expect(seen).toEqual(['What led to the decision "Engagement model: 26-week phased build"?']);
    } finally {
      window.removeEventListener(TOUR_PREFILL_EVENT, onPrefill);
    }
  });

  it("skip dismisses and persists for the session", async () => {
    const user = userEvent.setup();
    const { unmount } = render(<TourProvider />);
    await user.click(await screen.findByTestId("demo-tour-skip"));
    expect(screen.queryByTestId("demo-tour-popover")).toBeNull();
    expect(window.sessionStorage.getItem(TOUR_DISMISSED_KEY)).toBe("1");
    // A remount (navigation) stays dismissed.
    unmount();
    render(<TourProvider />);
    expect(screen.queryByTestId("demo-tour-popover")).toBeNull();
  });

  it("Escape skips from anywhere", async () => {
    const user = userEvent.setup();
    render(<TourProvider />);
    await screen.findByTestId("demo-tour-popover");
    await user.keyboard("{Escape}");
    expect(screen.queryByTestId("demo-tour-popover")).toBeNull();
    expect(window.sessionStorage.getItem(TOUR_DISMISSED_KEY)).toBe("1");
  });

  it("Back/Next move through manual steps; Back disabled on step 1", async () => {
    window.sessionStorage.setItem(TOUR_STEP_KEY, String(stepIndexOf("brief-delta")));
    const user = userEvent.setup();
    render(<TourProvider />);
    await screen.findByTestId("demo-tour-popover");
    await user.click(screen.getByTestId("demo-tour-next"));
    expect(screen.getByTestId("demo-tour-popover").getAttribute("data-tour-step")).toBe(
      "brief-needs-you",
    );
    await user.click(screen.getByTestId("demo-tour-back"));
    await user.click(screen.getByTestId("demo-tour-back"));
    expect(screen.getByTestId("demo-tour-popover").getAttribute("data-tour-step")).toBe(
      "portfolio-open-deal",
    );
    expect(screen.getByTestId("demo-tour-back")).toHaveProperty("disabled", true);
  });

  it("finale shows overview/repo links and Restart returns to step 1", async () => {
    window.sessionStorage.setItem(TOUR_STEP_KEY, String(stepIndexOf("finale")));
    const user = userEvent.setup();
    render(<TourProvider />);
    await screen.findByTestId("demo-tour-popover");
    expect(screen.getByText("Product overview").closest("a")?.getAttribute("href")).toBe(
      "/overview",
    );
    expect(screen.getByText("GitHub repo").closest("a")?.getAttribute("href")).toContain(
      "github.com",
    );
    await user.click(screen.getByTestId("demo-tour-restart"));
    expect(screen.getByTestId("demo-tour-popover").getAttribute("data-tour-step")).toBe(
      "portfolio-open-deal",
    );
    expect(window.sessionStorage.getItem(TOUR_DISMISSED_KEY)).toBeNull();
  });

  it("Done on the finale ends the tour and persists dismissal", async () => {
    window.sessionStorage.setItem(TOUR_STEP_KEY, String(stepIndexOf("finale")));
    const user = userEvent.setup();
    render(<TourProvider />);
    await user.click(await screen.findByTestId("demo-tour-next"));
    expect(screen.queryByTestId("demo-tour-popover")).toBeNull();
    expect(window.sessionStorage.getItem(TOUR_DISMISSED_KEY)).toBe("1");
  });

  it("capture-prefill button fetches the artifact and dispatches the capture-prefill event", async () => {
    window.sessionStorage.setItem(TOUR_STEP_KEY, String(stepIndexOf("slip-monday-kickoff")));
    const user = userEvent.setup();
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      text: () => Promise.resolve("Acme Robotics — Pilot Deployment Kickoff…"),
    });
    vi.stubGlobal("fetch", fetchMock);
    const seen: Array<{ text?: string; source?: string }> = [];
    const onPrefill = (e: Event) => {
      seen.push((e as CustomEvent<{ text?: string; source?: string }>).detail ?? {});
    };
    window.addEventListener(TOUR_CAPTURE_PREFILL_EVENT, onPrefill);
    try {
      render(<TourProvider />);
      await user.click(await screen.findByTestId("demo-tour-capture-prefill"));
      await waitFor(() => expect(seen).toHaveLength(1));
      expect(fetchMock).toHaveBeenCalledWith("/demo/kickoff-transcript.txt");
      expect(seen[0]).toEqual({
        text: "Acme Robotics — Pilot Deployment Kickoff…",
        source: "meeting_note",
      });
    } finally {
      window.removeEventListener(TOUR_CAPTURE_PREFILL_EVENT, onPrefill);
      vi.unstubAllGlobals();
    }
  });

  it("capture steps advance on the capture-done event (real state change)", async () => {
    window.sessionStorage.setItem(TOUR_STEP_KEY, String(stepIndexOf("slip-midweek-email")));
    render(<TourProvider />);
    await screen.findByTestId("demo-tour-popover");
    act(() => {
      window.dispatchEvent(
        new CustomEvent(TOUR_CAPTURE_DONE_EVENT, { detail: { proposalCount: 3 } }),
      );
    });
    await waitFor(() =>
      expect(screen.getByTestId("demo-tour-popover").getAttribute("data-tour-step")).toBe(
        "slip-midweek-caught",
      ),
    );
  });

  it("the standup step renders the .vtt download link", async () => {
    window.sessionStorage.setItem(TOUR_STEP_KEY, String(stepIndexOf("slip-thursday-standup")));
    render(<TourProvider />);
    await screen.findByTestId("demo-tour-popover");
    const link = screen.getByTestId("demo-tour-download");
    expect(link.getAttribute("href")).toBe("/demo/acme-standup.vtt");
    expect(link.hasAttribute("download")).toBe(true);
  });

  it("spotlights a present target and falls back to a centered dim when missing", async () => {
    window.sessionStorage.setItem(TOUR_STEP_KEY, String(stepIndexOf("brief-delta")));
    const { rerender } = render(
      <div>
        <section data-tour="brief-delta">Since you last looked</section>
        <TourProvider />
      </div>,
    );
    await screen.findByTestId("demo-tour-popover");
    await waitFor(() => expect(screen.getByTestId("demo-tour-spotlight")).toBeTruthy());
    // Target disappears → centered dim + popover with Next stays usable.
    rerender(
      <div>
        <TourProvider />
      </div>,
    );
    await waitFor(() => expect(screen.getByTestId("demo-tour-dim")).toBeTruthy());
    expect(screen.getByTestId("demo-tour-next")).toBeTruthy();
  });
});
