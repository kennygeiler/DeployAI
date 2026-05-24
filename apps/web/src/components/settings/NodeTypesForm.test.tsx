import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { CustomNodeType, NodeTypesResponse } from "@/lib/internal/node-types-cp";

import { NodeTypesForm } from "./NodeTypesForm.client";

const BUILTIN_LIST = [
  { name: "stakeholder", label: "Stakeholder" },
  { name: "organization", label: "Organization" },
  { name: "system", label: "System" },
];

function mkCustom(overrides: Partial<CustomNodeType> = {}): CustomNodeType {
  return {
    id: "nt1",
    name: "patient_journey",
    label: "Patient journey",
    color: "#fde68a",
    description: null,
    ...overrides,
  };
}

type Call = { url: string; method: string; body?: unknown };

function mockFetch(handlers: {
  listResponses?: Array<NodeTypesResponse>;
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

    if (method === "GET" && url === "/api/bff/tenant/node-types") {
      const resp = listResponses[Math.min(listIdx, listResponses.length - 1)];
      listIdx += 1;
      return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(resp) });
    }
    if (method === "POST" && url === "/api/bff/tenant/node-types") {
      return Promise.resolve({
        ok: true,
        status: 201,
        json: () => Promise.resolve(handlers.post ? handlers.post(parsedBody) : {}),
      });
    }
    if (method === "PUT" && url.startsWith("/api/bff/tenant/node-types/")) {
      return Promise.resolve({
        ok: true,
        status: 200,
        json: () => Promise.resolve(handlers.put ? handlers.put(parsedBody) : {}),
      });
    }
    if (method === "DELETE" && url.startsWith("/api/bff/tenant/node-types/")) {
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

describe("NodeTypesForm", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("renders builtins read-only with the built-in badge", async () => {
    mockFetch({ listResponses: [{ builtin: BUILTIN_LIST, custom: [] }] });
    render(<NodeTypesForm />);
    await waitFor(() => expect(screen.queryByText("Loading…")).toBeNull());
    expect(screen.getByText("Stakeholder")).toBeTruthy();
    expect(screen.getByText("Organization")).toBeTruthy();
    expect(screen.getAllByText("built-in").length).toBe(BUILTIN_LIST.length);
    expect(screen.getByText("No custom node types yet.")).toBeTruthy();
  });

  it("creates a custom node type and re-fetches the list", async () => {
    const { calls } = mockFetch({
      listResponses: [
        { builtin: BUILTIN_LIST, custom: [] },
        { builtin: BUILTIN_LIST, custom: [mkCustom()] },
      ],
      post: () => ({ node_type: mkCustom() }),
    });
    render(<NodeTypesForm />);
    await waitFor(() => expect(screen.queryByText("Loading…")).toBeNull());
    const user = userEvent.setup();
    await user.type(screen.getByLabelText("Slug"), "patient_journey");
    await user.type(screen.getByLabelText("Label"), "Patient journey");
    await user.click(screen.getByRole("button", { name: /create node type/i }));

    await waitFor(() => expect(screen.queryByText("Patient journey")).toBeTruthy());
    const post = calls.find((c) => c.method === "POST")!;
    expect(post.url).toBe("/api/bff/tenant/node-types");
    const body = post.body as { name: string; label: string };
    expect(body.name).toBe("patient_journey");
    expect(body.label).toBe("Patient journey");
  });

  it("surfaces the delete-in-use 409 with a helpful message", async () => {
    mockFetch({
      listResponses: [{ builtin: BUILTIN_LIST, custom: [mkCustom()] }],
      delResponse: {
        ok: false,
        status: 409,
        body: "node type is in use by one or more matrix nodes: patient_journey",
      },
    });
    const errorMod = await import("sonner");
    const errorSpy = vi.spyOn(errorMod.toast, "error");
    render(<NodeTypesForm />);
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
