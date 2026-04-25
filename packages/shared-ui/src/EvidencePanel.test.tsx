import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { EvidencePanel, renderHighlightedBody } from "./EvidencePanel";

const meta = {
  sourceType: "Meeting transcript",
  timestamp: "2026-04-23T10:03:00Z",
  phase: "P4 — Production",
  confidence: "0.91",
  supersession: "current" as const,
};

describe("renderHighlightedBody", () => {
  it("wraps the span in a single mark", () => {
    const { container } = render(
      <p>{renderHighlightedBody("The quick brown fox", { start: 4, end: 9, source_ref: "n1" })}</p>,
    );
    const marks = container.querySelectorAll("mark");
    expect(marks).toHaveLength(1);
    expect(marks[0]).toHaveTextContent("quick");
  });
});

describe("EvidencePanel", () => {
  it("exposes an article with labelled heading and a mark in loaded state", () => {
    render(
      <EvidencePanel
        retrievalPhase="oracle"
        metadata={meta}
        state="loaded"
        bodyText="Full sentence from memory."
        evidenceSpan={{ start: 5, end: 13, source_ref: "n1" }}
      />,
    );
    const article = screen.getByRole("article");
    expect(article).toHaveAttribute("aria-labelledby");
    screen.getByRole("heading", { name: "Evidence" });
    expect(article).toHaveAccessibleName(/Evidence/);
    const mark = within(article).getByText("sentence");
    expect(mark.tagName).toBe("MARK");
  });

  it("uses polite live region (sr-only) for state changes", () => {
    const { container } = render(
      <EvidencePanel retrievalPhase="cartographer" metadata={meta} state="loading" />,
    );
    const live = container.querySelector("[aria-live='polite']");
    expect(live).toBeInTheDocument();
  });
});
