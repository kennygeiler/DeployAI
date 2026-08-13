import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import JoinPage from "./page";

const fetchMock = vi.fn();

beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

function params(token = "tok-123") {
  return { params: Promise.resolve({ token }) };
}

describe("JoinPage (/join/[token])", () => {
  it("previews the invite and renders the accept form for a live token", async () => {
    fetchMock.mockResolvedValue(
      new Response(
        JSON.stringify({
          email: "teammate@acme.example",
          role: "deployment_strategist",
          workspace_name: "Acme",
          expires_at: "2026-08-20T00:00:00Z",
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      ),
    );
    render(await JoinPage(params()));
    await waitFor(() => expect(screen.getByText("Acme")).toBeInTheDocument());
    expect(fetchMock).toHaveBeenCalledWith("/api/auth/invites/preview?token=tok-123");
    expect(screen.getByText("deployment_strategist")).toBeInTheDocument();
    expect(screen.getByLabelText("Your name")).toBeInTheDocument();
    expect(screen.getByLabelText("Password")).toBeInTheDocument();
    expect(screen.getByLabelText("Confirm password")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Join workspace" })).toBeInTheDocument();
  });

  it("shows the generic dead-link message for invalid/expired/used tokens", async () => {
    fetchMock.mockResolvedValue(
      new Response(
        JSON.stringify({ error: "This invite link is invalid, expired, or already used." }),
        { status: 404, headers: { "Content-Type": "application/json" } },
      ),
    );
    render(await JoinPage(params("dead-token")));
    await waitFor(() =>
      expect(screen.getByRole("alert").textContent).toMatch(/invalid, expired, or already used/),
    );
    expect(screen.queryByRole("button", { name: "Join workspace" })).toBeNull();
  });
});
