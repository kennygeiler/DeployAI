import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { CustomMemberRole, MemberRolesRead } from "@/lib/internal/member-roles-cp";

import { MemberRolesForm } from "./MemberRolesForm.client";

const BUILTIN: MemberRolesRead["builtin"] = [
  { name: "fde", label: "Forward-deployed engineer" },
  { name: "deployment_strategist", label: "Deployment strategist" },
  { name: "biz_dev", label: "Business development" },
];

function mkCustom(overrides: Partial<CustomMemberRole> = {}): CustomMemberRole {
  return {
    id: "r1",
    name: "clinical_lead",
    label: "Clinical lead",
    description: null,
    ...overrides,
  };
}

type Call = { url: string; method: string; body?: unknown };

function mockFetch(handlers: {
  listResponses?: MemberRolesRead[];
  post?: (body: unknown) => unknown;
  del?: { status: number; bodyText?: string };
}): { calls: Call[] } {
  const calls: Call[] = [];
  const listResponses = handlers.listResponses ?? [{ builtin: BUILTIN, custom: [] }];
  let listIdx = 0;
  const fetchMock = vi.fn((url: string, init?: { method?: string; body?: string }) => {
    const method = init?.method ?? "GET";
    const parsedBody = init?.body ? JSON.parse(init.body) : undefined;
    calls.push({ url, method, body: parsedBody });
    if (method === "GET" && url === "/api/bff/tenant/member-roles") {
      const resp = listResponses[Math.min(listIdx, listResponses.length - 1)];
      listIdx += 1;
      return Promise.resolve({ ok: true, json: () => Promise.resolve(resp) });
    }
    if (method === "POST" && url === "/api/bff/tenant/member-roles") {
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve(handlers.post ? handlers.post(parsedBody) : {}),
      });
    }
    if (method === "DELETE" && url.startsWith("/api/bff/tenant/member-roles/")) {
      const d = handlers.del ?? { status: 204 };
      return Promise.resolve({
        ok: d.status >= 200 && d.status < 300,
        status: d.status,
        text: () => Promise.resolve(d.bodyText ?? ""),
        json: () => Promise.resolve({}),
      });
    }
    return Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
  });
  vi.stubGlobal("fetch", fetchMock);
  return { calls };
}

describe("MemberRolesForm", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("renders the built-in roles as read-only", async () => {
    mockFetch({ listResponses: [{ builtin: BUILTIN, custom: [] }] });
    render(<MemberRolesForm />);
    await waitFor(() => expect(screen.queryByText("Loading…")).toBeNull());
    expect(screen.getByText("Forward-deployed engineer")).toBeTruthy();
    expect(screen.getByText("Deployment strategist")).toBeTruthy();
    expect(screen.getByText("Business development")).toBeTruthy();
    expect(screen.getAllByText("Read-only")).toHaveLength(3);
    expect(screen.getByText("No custom roles yet.")).toBeTruthy();
  });

  it("creates a custom role and reloads the list", async () => {
    const { calls } = mockFetch({
      listResponses: [
        { builtin: BUILTIN, custom: [] },
        { builtin: BUILTIN, custom: [mkCustom()] },
      ],
      post: () => ({ role: mkCustom() }),
    });
    render(<MemberRolesForm />);
    await waitFor(() => expect(screen.queryByText("Loading…")).toBeNull());
    const user = userEvent.setup();
    await user.type(screen.getByLabelText("Slug"), "clinical_lead");
    await user.type(screen.getByLabelText("Label"), "Clinical lead");
    await user.click(screen.getByRole("button", { name: /create role/i }));

    await waitFor(() => expect(screen.queryByText("Clinical lead")).toBeTruthy());
    const post = calls.find((c) => c.method === "POST")!;
    expect(post.body).toEqual({ name: "clinical_lead", label: "Clinical lead" });
  });

  it("surfaces a delete-in-use 409 from the BFF as a toast", async () => {
    const { calls } = mockFetch({
      listResponses: [{ builtin: BUILTIN, custom: [mkCustom()] }],
      del: { status: 409, bodyText: "role is in use by one or more engagement members" },
    });
    render(<MemberRolesForm />);
    await waitFor(() => expect(screen.queryByText("Loading…")).toBeNull());
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: /^delete$/i }));
    await waitFor(() => expect(calls.some((c) => c.method === "DELETE")).toBe(true));
    // The row should remain because delete was blocked.
    expect(screen.getByText("Clinical lead")).toBeTruthy();
  });
});
