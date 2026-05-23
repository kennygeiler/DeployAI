import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

const { pushMock } = vi.hoisted(() => ({ pushMock: vi.fn() }));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: pushMock, replace: vi.fn(), back: vi.fn(), forward: vi.fn() }),
}));

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
    vi.unstubAllGlobals();
  });

  it("renders step 1 (LLM) first and shows the step counter", async () => {
    mockFetch(() => ({ ok: true, body: {} }));
    render(<OnboardingWizard />);
    expect(screen.getByText(/Step 1 of 3/)).toBeTruthy();
    expect(screen.getByLabelText("Provider")).toBeTruthy();
    expect(screen.getByLabelText("API key")).toBeTruthy();
    // No engagement form yet.
    expect(screen.queryByLabelText("Engagement name")).toBeNull();
  });

  it("flows through all three steps and redirects to the new engagement", async () => {
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

    // Step 1 — LLM (provider defaults to anthropic; type a key).
    await user.type(screen.getByLabelText("API key"), "sk-test-key");
    await user.click(screen.getByRole("button", { name: /continue/i }));

    // Step 2 — engagement.
    await waitFor(() => expect(screen.getByText(/Step 2 of 3/)).toBeTruthy());
    await user.type(screen.getByLabelText("Engagement name"), "Acme pilot");
    await user.click(screen.getByRole("button", { name: /create engagement/i }));

    // Step 3 — first member.
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
    // Member POST body wires the freshly-created user_id + the selected role.
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
    await user.type(screen.getByLabelText("API key"), "sk-x");
    await user.click(screen.getByRole("button", { name: /continue/i }));
    await waitFor(() => expect(screen.getByText(/invalid provider/)).toBeTruthy());
    // Still on step 1 — engagement form not shown.
    expect(screen.getByText(/Step 1 of 3/)).toBeTruthy();
  });
});
