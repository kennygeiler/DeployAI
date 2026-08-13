import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import SignupPage from "./page";

afterEach(() => {
  vi.unstubAllEnvs();
});

describe("SignupPage gate (NEXT_PUBLIC_SELF_SERVE_SIGNUP)", () => {
  it("404s (notFound) when signup is disabled", () => {
    // next/navigation's notFound() throws a control-flow error the app router
    // turns into the 404 page — in a unit render it surfaces as a throw.
    expect(() => render(<SignupPage />)).toThrow();
  });

  it("renders the full form when enabled", () => {
    vi.stubEnv("NEXT_PUBLIC_SELF_SERVE_SIGNUP", "1");
    render(<SignupPage />);
    expect(screen.getByLabelText("Workspace name")).toBeInTheDocument();
    expect(screen.getByLabelText("Your name")).toBeInTheDocument();
    expect(screen.getByLabelText("Email")).toBeInTheDocument();
    expect(screen.getByLabelText("Password")).toBeInTheDocument();
    expect(screen.getByLabelText("Confirm password")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Create workspace" })).toBeInTheDocument();
    const login = screen.getByText("Sign in").closest("a");
    expect(login?.getAttribute("href")).toBe("/login");
  });
});
