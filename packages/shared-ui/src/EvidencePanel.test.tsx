import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { EvidencePanel, renderHighlightedBody } from "./EvidencePanel";

const meta = {
  sourceType: "Meeting transcript",
  timestamp: "2026-04-23T10:03:00Z",
  phase: "P4 — Production",
  confidence: "0.91",
  supersession: "current" as const,
};

describe("renderHighlightedBody", () => {
  afterEach(() => {
    cleanup();
  });

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
  afterEach(() => {
    cleanup();
  });

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

  it("renders footer inside the article for loaded state (Story 8.4)", () => {
    render(
      <EvidencePanel
        retrievalPhase="oracle"
        metadata={meta}
        state="loaded"
        bodyText="Body"
        footer={<a href="/evidence/n1">Navigate to source</a>}
      />,
    );
    const article = screen.getByRole("article");
    expect(article.querySelector("[data-evidence-panel-footer]")).toBeInTheDocument();
    expect(within(article).getByRole("link", { name: /navigate to source/i })).toHaveAttribute(
      "href",
      "/evidence/n1",
    );
  });

  it("renders footer for degraded state (Story 8.4)", () => {
    render(
      <EvidencePanel
        retrievalPhase="oracle"
        metadata={meta}
        state="degraded"
        bodyText="Partial"
        evidenceSpan={{ start: 0, end: 4, source_ref: "r" }}
        footer={<a href="/evidence/n2">Navigate to source</a>}
      />,
    );
    const article = screen.getByRole("article");
    expect(within(article).getByRole("link", { name: /navigate to source/i })).toHaveAttribute(
      "href",
      "/evidence/n2",
    );
  });
});
