import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import LoginPage from "./page";

function params(q: { error?: string; next?: string } = {}) {
  return { searchParams: Promise.resolve(q) };
}

afterEach(() => {
  vi.unstubAllEnvs();
});

describe("LoginPage demo button (Wave 4S)", () => {
  it("hides the demo button when NEXT_PUBLIC_DEMO_MODE is unset", async () => {
    render(await LoginPage(params()));
    expect(screen.queryByText("View live demo")).toBeNull();
    expect(screen.getByText("Sign in with SSO")).toBeInTheDocument();
  });

  it("shows the demo button linking to /api/auth/demo when NEXT_PUBLIC_DEMO_MODE=1", async () => {
    vi.stubEnv("NEXT_PUBLIC_DEMO_MODE", "1");
    render(await LoginPage(params()));
    const link = screen.getByText("View live demo").closest("a");
    expect(link).not.toBeNull();
    expect(link?.getAttribute("href")).toBe("/api/auth/demo");
    expect(
      screen.getByText(/Read-only guest on a demo workspace — no sign-up needed\./),
    ).toBeInTheDocument();
    // K6 — the caption promises the guided tour and states the session length
    // (matches DEPLOYAI_DEMO_SESSION_TTL=3600 on the showcase deploy).
    expect(
      screen.getByText(/guided tour starts automatically \(sessions last about an hour\)/),
    ).toBeInTheDocument();
    // SSO stays available below the demo button.
    expect(screen.getByText("Sign in with SSO")).toBeInTheDocument();
  });

  it("renders the demo_unavailable error message", async () => {
    vi.stubEnv("NEXT_PUBLIC_DEMO_MODE", "1");
    render(await LoginPage(params({ error: "demo_unavailable" })));
    expect(screen.getByRole("alert").textContent).toMatch(/live demo is unavailable/);
  });
});
