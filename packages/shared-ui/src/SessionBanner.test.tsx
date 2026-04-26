import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { SessionBanner } from "./SessionBanner";

describe("SessionBanner", () => {
  it("renders session label and region", () => {
    const exp = Date.now() + 60_000;
    render(
      <SessionBanner
        sessionId="sess-test-0001"
        variant="break-glass"
        expiresAt={exp}
        nowMs={() => exp - 30_000}
      />,
    );
    expect(screen.getByRole("region", { name: /Break-glass session/i })).toBeInTheDocument();
    expect(screen.getByText(/sess-test-0001/)).toBeInTheDocument();
  });
});
