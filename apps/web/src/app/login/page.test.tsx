import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import LoginPage from "./page";

function params(q: { error?: string; next?: string } = {}) {
  return { searchParams: Promise.resolve(q) };
}

function stubOidcEnv() {
  vi.stubEnv("DEPLOYAI_OIDC_ISSUER", "https://issuer.example");
  vi.stubEnv("DEPLOYAI_OIDC_CLIENT_ID", "client-1");
  vi.stubEnv("DEPLOYAI_OIDC_REDIRECT_URI", "https://app.example.com/api/auth/callback/oidc");
}

afterEach(() => {
  vi.unstubAllEnvs();
});

describe("LoginPage email/password form (self-serve accounts)", () => {
  it("always renders the email/password form", async () => {
    render(await LoginPage(params()));
    expect(screen.getByLabelText("Email")).toBeInTheDocument();
    expect(screen.getByLabelText("Password")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Sign in" })).toBeInTheDocument();
  });

  it("hides the signup link unless NEXT_PUBLIC_SELF_SERVE_SIGNUP=1", async () => {
    render(await LoginPage(params()));
    expect(screen.queryByText("Create a workspace")).toBeNull();
  });

  it("shows the signup link when NEXT_PUBLIC_SELF_SERVE_SIGNUP=1", async () => {
    vi.stubEnv("NEXT_PUBLIC_SELF_SERVE_SIGNUP", "1");
    render(await LoginPage(params()));
    const link = screen.getByText("Create a workspace").closest("a");
    expect(link?.getAttribute("href")).toBe("/signup");
  });
});

describe("LoginPage SSO button (enterprise OIDC option)", () => {
  it("hides the SSO button when OIDC is not configured", async () => {
    render(await LoginPage(params()));
    expect(screen.queryByText("Sign in with SSO")).toBeNull();
  });

  it("shows the SSO button when the OIDC envs are configured", async () => {
    stubOidcEnv();
    render(await LoginPage(params()));
    const link = screen.getByText("Sign in with SSO").closest("a");
    expect(link?.getAttribute("href")).toBe("/api/auth/login");
  });
});

describe("LoginPage demo button (Wave 4S)", () => {
  it("hides the demo button when NEXT_PUBLIC_DEMO_MODE is unset", async () => {
    stubOidcEnv();
    render(await LoginPage(params()));
    expect(screen.queryByText("View live demo")).toBeNull();
    expect(screen.getByText("Sign in with SSO")).toBeInTheDocument();
  });

  it("shows the demo button linking to /api/auth/demo when NEXT_PUBLIC_DEMO_MODE=1", async () => {
    stubOidcEnv();
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
