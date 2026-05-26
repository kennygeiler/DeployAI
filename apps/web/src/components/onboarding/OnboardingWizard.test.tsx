import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

const { pushMock, toastMock, toastSuccessMock } = vi.hoisted(() => ({
  pushMock: vi.fn(),
  toastMock: vi.fn(),
  toastSuccessMock: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: pushMock, replace: vi.fn(), back: vi.fn(), forward: vi.fn() }),
}));

vi.mock("sonner", () => {
  const t = Object.assign(toastMock, { success: toastSuccessMock });
  return { toast: t };
});

import { OnboardingWizard } from "./OnboardingWizard.client";

type CallRecord = { url: string; method: string; body?: unknown };

function mockFetch(handler: (call: CallRecord) => { ok: boolean; status?: number; body: unknown }) {
  const calls: CallRecord[] = [];
  const fetchMock = vi.fn((url: string, init?: { method?: string; body?: string }) => {
    const method = init?.method ?? "GET";
    const parsedBody = init?.body ? JSON.parse(init.body) : undefined;
    const record: CallRecord = { url, method, body: parsedBody };
    calls.push(record);
    const res = handler(record);
    return Promise.resolve({
      ok: res.ok,
      status: res.status ?? (res.ok ? 200 : 400),
      json: () => Promise.resolve(res.body),
      text: () =>
        Promise.resolve(typeof res.body === "string" ? res.body : JSON.stringify(res.body)),
    });
  });
  vi.stubGlobal("fetch", fetchMock);
  return calls;
}

describe("OnboardingWizard", () => {
  afterEach(() => {
    pushMock.mockReset();
    toastMock.mockReset();
    toastSuccessMock.mockReset();
    vi.unstubAllGlobals();
  });

  it("renders the picker (step 0) with both load and start-fresh buttons", async () => {
    mockFetch(() => ({ ok: true, body: {} }));
    render(<OnboardingWizard />);
    expect(screen.getByText(/Start —/)).toBeTruthy();
    expect(screen.getByRole("button", { name: /Load BlueState demo/i })).toBeTruthy();
    expect(screen.getByRole("button", { name: /Start fresh/i })).toBeTruthy();
    expect(screen.queryByLabelText("Provider")).toBeNull();
  });

  it("'Load BlueState demo' POSTs the BFF route and redirects on success", async () => {
    const calls = mockFetch((call) => {
      if (call.url === "/api/bff/onboarding/seed-bluestate" && call.method === "POST") {
        return {
          ok: true,
          body: {
            engagement_id: "dddddddd-dddd-4ddd-8ddd-dddddddddddd",
            summary: {
              tenant_id: "11111111-1111-1111-1111-111111111111",
              engagement_id: "dddddddd-dddd-4ddd-8ddd-dddddddddddd",
              stakeholder_nodes: 10,
              decision_nodes: 12,
              risks: 4,
              snapshot_count: 182,
              temporal_insight_count: 5,
            },
            took_seconds: 18.5,
            source: "cp",
          },
        };
      }
      return { ok: false, body: "unexpected" };
    });

    const user = userEvent.setup();
    render(<OnboardingWizard />);
    await user.click(screen.getByRole("button", { name: /Load BlueState demo/i }));

    await waitFor(() =>
      expect(pushMock).toHaveBeenCalledWith("/engagements/dddddddd-dddd-4ddd-8ddd-dddddddddddd"),
    );
    expect(calls[0]?.url).toBe("/api/bff/onboarding/seed-bluestate");
    expect(calls[0]?.method).toBe("POST");
    expect(calls[0]?.body as { force: boolean }).toEqual({ force: false });
    expect(toastSuccessMock).toHaveBeenCalled();
  });

  it("'Load BlueState demo' surfaces an 'already seeded' toast on 409", async () => {
    mockFetch((call) => {
      if (call.url === "/api/bff/onboarding/seed-bluestate" && call.method === "POST") {
        return {
          ok: false,
          status: 409,
          body: {
            error: "already_seeded",
            engagement_id: "dddddddd-dddd-4ddd-8ddd-dddddddddddd",
          },
        };
      }
      return { ok: false, body: "unexpected" };
    });

    const user = userEvent.setup();
    render(<OnboardingWizard />);
    await user.click(screen.getByRole("button", { name: /Load BlueState demo/i }));

    await waitFor(() => expect(toastMock).toHaveBeenCalled());
    const firstCall = toastMock.mock.calls[0];
    expect(firstCall?.[0]).toMatch(/already seeded/i);
    expect(pushMock).not.toHaveBeenCalled();
  });

  it("'Start fresh' reveals step 1 (LLM form)", async () => {
    mockFetch(() => ({ ok: true, body: {} }));
    const user = userEvent.setup();
    render(<OnboardingWizard />);
    await user.click(screen.getByRole("button", { name: /Start fresh/i }));
    await waitFor(() => expect(screen.getByText(/Step 1 of 3/)).toBeTruthy());
    expect(screen.getByLabelText("Provider")).toBeTruthy();
    expect(screen.getByLabelText("API key")).toBeTruthy();
  });

  it("flows through all three steps after start-fresh and redirects to the new engagement", async () => {
    const calls = mockFetch((call) => {
      if (call.url === "/api/bff/tenant/llm-config" && call.method === "PUT") {
        return { ok: true, body: { config: { provider: "stub" } } };
      }
      if (call.url === "/api/bff/engagements" && call.method === "POST") {
        return { ok: true, status: 201, body: { engagement: { id: "eng-1", name: "Acme" } } };
      }
      if (call.url === "/api/bff/tenant/users" && call.method === "POST") {
        return { ok: true, status: 201, body: { user: { id: "user-1", user_name: "kenny" } } };
      }
      if (call.url === "/api/bff/engagements/eng-1/members" && call.method === "POST") {
        return { ok: true, status: 201, body: { member: { id: "mem-1" } } };
      }
      return { ok: false, body: "unexpected" };
    });

    const user = userEvent.setup();
    render(<OnboardingWizard />);

    await user.click(screen.getByRole("button", { name: /Start fresh/i }));
    await waitFor(() => expect(screen.getByLabelText("API key")).toBeTruthy());
    await user.type(screen.getByLabelText("API key"), "sk-test-key");
    await user.click(screen.getByRole("button", { name: /continue/i }));

    await waitFor(() => expect(screen.getByText(/Step 2 of 3/)).toBeTruthy());
    await user.type(screen.getByLabelText("Engagement name"), "Acme pilot");
    await user.click(screen.getByRole("button", { name: /create engagement/i }));

    await waitFor(() => expect(screen.getByText(/Step 3 of 3/)).toBeTruthy());
    await user.type(screen.getByLabelText("Username"), "kenny");
    await user.click(screen.getByRole("button", { name: /finish setup/i }));

    await waitFor(() => expect(pushMock).toHaveBeenCalledWith("/engagements/eng-1"));

    const methods = calls.map((c) => `${c.method} ${c.url}`);
    expect(methods).toEqual([
      "PUT /api/bff/tenant/llm-config",
      "POST /api/bff/engagements",
      "POST /api/bff/tenant/users",
      "POST /api/bff/engagements/eng-1/members",
    ]);
    const memberCall = calls[3];
    expect(memberCall).toBeDefined();
    expect(memberCall!.body as { user_id: string; role: string }).toEqual({
      user_id: "user-1",
      role: "deployment_strategist",
    });
  });

  it("surfaces a server error from step 1 and stays on step 1", async () => {
    mockFetch(() => ({ ok: false, status: 422, body: "invalid provider" }));
    const user = userEvent.setup();
    render(<OnboardingWizard />);
    await user.click(screen.getByRole("button", { name: /Start fresh/i }));
    await waitFor(() => expect(screen.getByLabelText("API key")).toBeTruthy());
    await user.type(screen.getByLabelText("API key"), "sk-x");
    await user.click(screen.getByRole("button", { name: /continue/i }));
    await waitFor(() => expect(screen.getByText(/invalid provider/)).toBeTruthy());
    expect(screen.getByText(/Step 1 of 3/)).toBeTruthy();
  });
});
