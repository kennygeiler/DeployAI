import { render, screen, within } from "@testing-library/react";
import { beforeAll, describe, expect, it } from "vitest";

import { OverviewDeck } from "./OverviewDeck.client";

beforeAll(() => {
  // jsdom has no IntersectionObserver; the deck uses it to track the
  // active slide for the progress dots.
  class IntersectionObserverStub {
    observe() {}
    unobserve() {}
    disconnect() {}
    takeRecords() {
      return [];
    }
  }
  Object.defineProperty(globalThis, "IntersectionObserver", {
    writable: true,
    value: IntersectionObserverStub,
  });
});

const EXPECTED_SLIDES = [
  "What DeployAI is",
  "Portfolio",
  "The Brief",
  "The capture → review loop",
  "Ask Kenny",
  "Citations and receipts",
  "Review inbox and the knowledge flywheel",
  "The graph lens",
  "Where things live",
  "Run the demo",
];

const EXPECTED_SCREENSHOTS = [
  "/overview/portfolio.png",
  "/overview/brief-since-you-last-looked.png",
  "/overview/needs-you-queue.png",
  "/overview/ask-bar.png",
  "/overview/kenny-chat-answer.png",
  "/overview/citation-evidence-panel.png",
  "/overview/review-inbox.png",
  "/overview/graph-lens.png",
];

describe("OverviewDeck", () => {
  it("renders every slide as a labelled section", () => {
    render(<OverviewDeck />);
    const deck = screen.getByTestId("overview-deck");
    for (const title of EXPECTED_SLIDES) {
      expect(within(deck).getByRole("region", { name: title })).toBeInTheDocument();
    }
  });

  it("references all eight product screenshots with alt text", () => {
    render(<OverviewDeck />);
    const images = screen.getAllByRole("img");
    const sources = images.map((img) => {
      // next/image rewrites src via its loader; the original path survives
      // as a substring (unoptimized images keep it verbatim).
      return decodeURIComponent(img.getAttribute("src") ?? "");
    });
    for (const path of EXPECTED_SCREENSHOTS) {
      expect(sources.some((s) => s.includes(path))).toBe(true);
    }
    for (const img of images) {
      expect((img.getAttribute("alt") ?? "").length).toBeGreaterThan(20);
    }
  });

  it("exposes keyboard + dot navigation landmarks", () => {
    render(<OverviewDeck />);
    // Deck is a focusable region so PageUp/PageDown paging is reachable.
    const deck = screen.getByRole("region", { name: "Product overview slides" });
    expect(deck).toHaveAttribute("tabindex", "0");
    // One progress dot per slide, plus the visible skip affordance.
    const dots = within(screen.getByRole("navigation", { name: "Slide navigation" })).getAllByRole(
      "button",
    );
    expect(dots).toHaveLength(EXPECTED_SLIDES.length);
    expect(screen.getByRole("button", { name: "Skip to the end" })).toBeInTheDocument();
  });

  it("lists the sidebar destinations on the nav-map slide", () => {
    render(<OverviewDeck />);
    const navMap = screen.getByRole("region", { name: "Where things live" });
    for (const name of ["Engagements", "Review inbox", "Search", "Settings", "Admin"]) {
      expect(within(navMap).getByText(name)).toBeInTheDocument();
    }
  });
});
