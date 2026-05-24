import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { CustomMemberRole, MemberRolesResponse } from "@/lib/internal/member-roles-cp";

import { MemberRolesForm } from "./MemberRolesForm.client";

const BUILTIN_LIST = [
  { name: "fde", label: "Forward-deployed engineer" },
  { name: "deployment_strategist", label: "Deployment strategist" },
  { name: "biz_dev", label: "Business development" },
];

function mkCustom(overrides: Partial<CustomMemberRole> = {}): CustomMemberRole {
  return {
    id: "mr1",
    name: "clinical_lead",
    label: "Clinical lead",
    description: null,
    ...overrides,
  };
}

type Call = { url: string; method: string; body?: unknown };

function mockFetch(handlers: {
  listResponses?: Array<MemberRolesResponse>;
  post?: (body: unknown) => unknown;
  put?: (body: unknown) => unknown;
  delResponse?: { ok: boolean; status: number; body?: string };
}): { calls: Call[] } {
  const calls: Call[] = [];
  const listResponses = handlers.listResponses ?? [{ builtin: BUILTIN_LIST, custom: [] }];
  let listIdx = 0;
  const fetchMock = vi.fn((url: string, init?: { method?: string; body?: string }) => {
    const method = init?.method ?? "GET";
    const parsedBody = init?.body ? JSON.parse(init.body) : undefined;
    calls.push({ url, method, body: parsedBody });

    if (method === "GET" && url === "/api/bff/tenant/member-roles") {
      const resp = listResponses[Math.min(listIdx, listResponses.length - 1)];
      listIdx += 1;
      return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(resp) });
    }
    if (method === "POST" && url === "/api/bff/tenant/member-roles") {
      return Promise.resolve({
        ok: true,
        status: 201,
        json: () => Promise.resolve(handlers.post ? handlers.post(parsedBody) : {}),
      });
    }
    if (method === "PUT" && url.startsWith("/api/bff/tenant/member-roles/")) {
      return Promise.resolve({
        ok: true,
        status: 200,
        json: () => Promise.resolve(handlers.put ? handlers.put(parsedBody) : {}),
      });
    }
    if (method === "DELETE" && url.startsWith("/api/bff/tenant/member-roles/")) {
      const r = handlers.delResponse ?? { ok: true, status: 204 };
      return Promise.resolve({
        ok: r.ok,
        status: r.status,
        text: () => Promise.resolve(r.body ?? ""),
        json: () => Promise.resolve({}),
      });
    }
    return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({}) });
  });
  vi.stubGlobal("fetch", fetchMock);
  return { calls };
}

describe("MemberRolesForm", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("renders builtins read-only with the built-in badge and empty custom state", async () => {
    mockFetch({ listResponses: [{ builtin: BUILTIN_LIST, custom: [] }] });
    render(<MemberRolesForm />);
    await waitFor(() => expect(screen.queryByText("Loading…")).toBeNull());
    expect(screen.getByText("Forward-deployed engineer")).toBeTruthy();
    expect(screen.getByText("Deployment strategist")).toBeTruthy();
    expect(screen.getByText("Business development")).toBeTruthy();
    expect(screen.getAllByText("built-in").length).toBe(BUILTIN_LIST.length);
    expect(screen.getByText("No custom member roles yet.")).toBeTruthy();
  });

  it("creates a custom role and re-fetches the list", async () => {
    const { calls } = mockFetch({
      listResponses: [
        { builtin: BUILTIN_LIST, custom: [] },
        { builtin: BUILTIN_LIST, custom: [mkCustom()] },
      ],
      post: () => ({ member_role: mkCustom() }),
    });
    render(<MemberRolesForm />);
    await waitFor(() => expect(screen.queryByText("Loading…")).toBeNull());
    const user = userEvent.setup();
    await user.type(screen.getByLabelText("Slug"), "clinical_lead");
    await user.type(screen.getByLabelText("Label"), "Clinical lead");
    await user.click(screen.getByRole("button", { name: /create member role/i }));

    await waitFor(() => expect(screen.queryByText("Clinical lead")).toBeTruthy());
    const post = calls.find((c) => c.method === "POST")!;
    expect(post.url).toBe("/api/bff/tenant/member-roles");
    const body = post.body as { name: string; label: string };
    expect(body.name).toBe("clinical_lead");
    expect(body.label).toBe("Clinical lead");
  });

  it("surfaces the delete-in-use 409 with a helpful message", async () => {
    mockFetch({
      listResponses: [{ builtin: BUILTIN_LIST, custom: [mkCustom()] }],
      delResponse: {
        ok: false,
        status: 409,
        body: "member role is in use by one or more engagement members: clinical_lead",
      },
    });
    const errorMod = await import("sonner");
    const errorSpy = vi.spyOn(errorMod.toast, "error");
    render(<MemberRolesForm />);
    await waitFor(() => expect(screen.queryByText("Loading…")).toBeNull());
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: /delete/i }));

    await waitFor(() => {
      expect(errorSpy).toHaveBeenCalled();
    });
    const call = errorSpy.mock.calls[0]!;
    const title = call[0] as string;
    const opts = call[1] as { description?: string } | undefined;
    expect(title).toMatch(/Cannot delete/i);
    expect(opts?.description ?? "").toMatch(/in use/i);
    errorSpy.mockRestore();
  });
});
