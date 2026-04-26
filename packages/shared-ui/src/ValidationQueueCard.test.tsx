import { fireEvent, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { ValidationQueueCard } from "./ValidationQueueCard";

const base = {
  proposedFact: "NYC DOT committed to Section 15 cable scope by Q2.",
  supportingEvidence: <span data-testid="ev">evidence</span>,
  confidence: "0.88",
  onConfirm: vi.fn(),
  onModify: vi.fn(),
  onReject: vi.fn(),
  onDefer: vi.fn(),
};

describe("ValidationQueueCard", () => {
  it("renders as article with titled proposed fact", () => {
    const { container } = render(
      <ValidationQueueCard
        {...base}
        state="unresolved"
        onConfirm={base.onConfirm}
        onModify={base.onModify}
        onReject={base.onReject}
        onDefer={base.onDefer}
      />,
    );
    const articles = container.querySelectorAll("article");
    expect(articles.length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByRole("heading", { name: "Proposed fact" }).length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText(/NYC DOT committed/)).toBeInTheDocument();
  });

  it("requires a reason for modify, then calls onModify with text", async () => {
    const user = userEvent.setup();
    const onModify = vi.fn().mockResolvedValue(undefined);
    render(
      <ValidationQueueCard
        {...base}
        state="unresolved"
        onConfirm={base.onConfirm}
        onModify={onModify}
        onReject={base.onReject}
        onDefer={base.onDefer}
      />,
    );
    const lastCard = () => screen.getAllByTestId("validation-queue-card").pop()!;
    const inCard = () => within(lastCard());
    await user.click(inCard().getByRole("button", { name: "Modify proposal" }));
    expect(onModify).not.toHaveBeenCalled();
    expect(inCard().getByRole("alert")).toHaveTextContent(/Add a reason/);
    const ta = inCard().getByRole("textbox", { name: /Response reason/i });
    fireEvent.change(ta, { target: { value: "Tighten scope to manhole covers only." } });
    await user.click(inCard().getByRole("button", { name: "Modify proposal" }));
    expect(onModify).toHaveBeenCalledWith("Tighten scope to manhole covers only.");
  });
});
