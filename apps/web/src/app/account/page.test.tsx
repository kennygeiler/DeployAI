import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import AccountPage from "./page";

const fetchMock = vi.fn();

function meJson(roles: string[], hasPassword = true): Response {
  return new Response(
    JSON.stringify({
      user_id: "22222222-2222-2222-2222-222222222222",
      tenant_id: "11111111-1111-1111-1111-111111111111",
      tenant_name: "Acme",
      email: "kim@example.com",
      display_name: "Kim",
      roles,
      has_password: hasPassword,
    }),
    { status: 200, headers: { "Content-Type": "application/json" } },
  );
}

function pendingJson(): Response {
  return new Response(JSON.stringify([]), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });
}

beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("AccountPage", () => {
  it("renders profile, change-password, and sign-out for a strategist (no invites)", async () => {
    fetchMock.mockImplementation((url: string) =>
      String(url).includes("/api/auth/me")
        ? Promise.resolve(meJson(["deployment_strategist"]))
        : Promise.resolve(pendingJson()),
    );
    render(<AccountPage />);
    await waitFor(() => expect(screen.getByText("kim@example.com")).toBeInTheDocument());
    expect(screen.getByText("Acme")).toBeInTheDocument();
    expect(screen.getByText("deployment_strategist")).toBeInTheDocument();
    expect(screen.getByLabelText("Current password")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Sign out" })).toBeInTheDocument();
    expect(screen.queryByText("Invite teammates")).toBeNull();
  });

  it("shows the invites section for customer_admin, including the no-email note", async () => {
    fetchMock.mockImplementation((url: string) =>
      String(url).includes("/api/auth/me")
        ? Promise.resolve(meJson(["customer_admin"]))
        : Promise.resolve(pendingJson()),
    );
    render(<AccountPage />);
    await waitFor(() => expect(screen.getByText("Invite teammates")).toBeInTheDocument());
    expect(screen.getByText(/No email is sent/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Create invite link" })).toBeInTheDocument();
  });

  it("hides the change-password form for SSO-only users", async () => {
    fetchMock.mockImplementation((url: string) =>
      String(url).includes("/api/auth/me")
        ? Promise.resolve(meJson(["deployment_strategist"], false))
        : Promise.resolve(pendingJson()),
    );
    render(<AccountPage />);
    await waitFor(() =>
      expect(screen.getByText(/signs in with SSO; there is no password/)).toBeInTheDocument(),
    );
    expect(screen.queryByLabelText("Current password")).toBeNull();
  });

  it("shows the error state when /api/auth/me rejects", async () => {
    fetchMock.mockResolvedValue(
      new Response(JSON.stringify({ error: "not signed in" }), { status: 401 }),
    );
    render(<AccountPage />);
    await waitFor(() => expect(screen.getByRole("alert").textContent).toMatch(/not signed in/));
  });
});
