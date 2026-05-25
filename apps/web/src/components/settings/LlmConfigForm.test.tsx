import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { TenantLlmConfig } from "@/lib/internal/llm-config-cp";

import { LlmConfigForm } from "./LlmConfigForm.client";

function mkCfg(overrides: Partial<TenantLlmConfig> = {}): TenantLlmConfig {
  return {
    tenant_id: "t1",
    provider: "anthropic",
    model_name: "claude-opus-4-5",
    api_key_masked: "sk-a****wxyz",
    has_api_key: true,
    secondary_provider: null,
    secondary_model_name: null,
    secondary_api_key_masked: null,
    has_secondary_api_key: false,
    updated_at: "2026-05-23T12:00:00Z",
    ...overrides,
  };
}

function mockFetch(handlers: { get?: () => unknown; put?: (body: unknown) => unknown }) {
  const calls: Array<{ url: string; method: string; body?: unknown }> = [];
  const fetchMock = vi.fn((url: string, init?: { method?: string; body?: string }) => {
    const method = init?.method ?? "GET";
    const parsedBody = init?.body ? JSON.parse(init.body) : undefined;
    calls.push({ url, method, body: parsedBody });
    if (method === "GET" && handlers.get) {
      return Promise.resolve({ ok: true, json: () => Promise.resolve(handlers.get!()) });
    }
    if (method === "PUT" && handlers.put) {
      return Promise.resolve({ ok: true, json: () => Promise.resolve(handlers.put!(parsedBody)) });
    }
    return Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
  });
  vi.stubGlobal("fetch", fetchMock);
  return calls;
}

describe("LlmConfigForm", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("renders the unconfigured empty state and hints env fallback", async () => {
    mockFetch({ get: () => ({ config: null }) });
    render(<LlmConfigForm />);
    await waitFor(() => expect(screen.queryByText("Loading…")).toBeNull());
    expect(screen.getByText(/Not configured yet/)).toBeTruthy();
    expect(screen.getByLabelText("Provider")).toBeTruthy();
    expect(screen.getByLabelText("Model")).toBeTruthy();
    expect(screen.getByLabelText("API key")).toBeTruthy();
  });

  it("prefills provider + model when a saved config exists, masks the key", async () => {
    mockFetch({ get: () => ({ config: mkCfg() }) });
    render(<LlmConfigForm />);
    await waitFor(() => expect(screen.queryByText("Loading…")).toBeNull());
    const provider = screen.getByLabelText("Provider") as HTMLSelectElement;
    expect(provider.value).toBe("anthropic");
    const model = screen.getByLabelText("Model") as HTMLInputElement;
    expect(model.value).toBe("claude-opus-4-5");
    // Masked fingerprint is in the placeholder; no raw key in the DOM.
    const key = screen.getByLabelText("API key") as HTMLInputElement;
    expect(key.placeholder).toBe("sk-a****wxyz");
    expect(key.value).toBe("");
  });

  it("PUTs without api_key when user only edits the model", async () => {
    const calls = mockFetch({
      get: () => ({ config: mkCfg() }),
      put: (body) => ({
        config: { ...mkCfg(), model_name: (body as { model_name: string }).model_name },
      }),
    });
    render(<LlmConfigForm />);
    await waitFor(() => expect(screen.queryByText("Loading…")).toBeNull());
    const model = screen.getByLabelText("Model") as HTMLInputElement;
    const user = userEvent.setup();
    await user.clear(model);
    await user.type(model, "claude-haiku-4-5");
    await user.click(screen.getByRole("button", { name: /save/i }));
    await waitFor(() => expect(calls.some((c) => c.method === "PUT")).toBe(true));
    const put = calls.find((c) => c.method === "PUT")!;
    expect((put.body as { model_name: string }).model_name).toBe("claude-haiku-4-5");
    expect("api_key" in (put.body as object)).toBe(false);
    // Failover stays off → secondary trio is all nulls (toggle off contract).
    const sent = put.body as {
      secondary_provider: unknown;
      secondary_model_name: unknown;
      secondary_api_key: unknown;
    };
    expect(sent.secondary_provider).toBeNull();
    expect(sent.secondary_model_name).toBeNull();
    expect(sent.secondary_api_key).toBeNull();
  });

  it("PUTs api_key when user types a new key, then clears the input on success", async () => {
    const calls = mockFetch({
      get: () => ({ config: mkCfg() }),
      put: () => ({ config: mkCfg({ api_key_masked: "sk-n****newk" }) }),
    });
    render(<LlmConfigForm />);
    await waitFor(() => expect(screen.queryByText("Loading…")).toBeNull());
    const key = screen.getByLabelText("API key") as HTMLInputElement;
    const user = userEvent.setup();
    await user.type(key, "sk-new-key-value");
    await user.click(screen.getByRole("button", { name: /save/i }));
    await waitFor(() => expect(calls.some((c) => c.method === "PUT")).toBe(true));
    const put = calls.find((c) => c.method === "PUT")!;
    expect((put.body as { api_key: string }).api_key).toBe("sk-new-key-value");
    // After save the input is cleared and the masked placeholder reflects the new key.
    await waitFor(() => expect(key.value).toBe(""));
  });

  it("does not render the failover inputs until the toggle is on", async () => {
    mockFetch({ get: () => ({ config: mkCfg() }) });
    render(<LlmConfigForm />);
    await waitFor(() => expect(screen.queryByText("Loading…")).toBeNull());
    expect(screen.getByLabelText("Enable failover")).toBeTruthy();
    expect(screen.queryByLabelText("Secondary provider")).toBeNull();
    expect(screen.queryByLabelText("Secondary model")).toBeNull();
    expect(screen.queryByLabelText("Secondary API key")).toBeNull();
  });

  it("prefills failover inputs from a saved config and masks the secondary key", async () => {
    mockFetch({
      get: () => ({
        config: mkCfg({
          secondary_provider: "openai",
          secondary_model_name: "gpt-4o",
          secondary_api_key_masked: "sk-o****9876",
          has_secondary_api_key: true,
        }),
      }),
    });
    render(<LlmConfigForm />);
    await waitFor(() => expect(screen.queryByText("Loading…")).toBeNull());
    const toggle = screen.getByLabelText("Enable failover") as HTMLInputElement;
    expect(toggle.checked).toBe(true);
    const secondaryProvider = screen.getByLabelText("Secondary provider") as HTMLSelectElement;
    expect(secondaryProvider.value).toBe("openai");
    const secondaryModel = screen.getByLabelText("Secondary model") as HTMLInputElement;
    expect(secondaryModel.value).toBe("gpt-4o");
    const secondaryKey = screen.getByLabelText("Secondary API key") as HTMLInputElement;
    expect(secondaryKey.placeholder).toBe("sk-o****9876");
    expect(secondaryKey.value).toBe("");
  });

  it("PUTs the full secondary trio when the user enables failover", async () => {
    const calls = mockFetch({
      get: () => ({ config: mkCfg() }),
      put: () => ({
        config: mkCfg({
          secondary_provider: "openai",
          secondary_model_name: "gpt-4o",
          secondary_api_key_masked: "sk-o****9876",
          has_secondary_api_key: true,
        }),
      }),
    });
    render(<LlmConfigForm />);
    await waitFor(() => expect(screen.queryByText("Loading…")).toBeNull());
    const user = userEvent.setup();
    await user.click(screen.getByLabelText("Enable failover"));
    await user.type(screen.getByLabelText("Secondary model"), "gpt-4o");
    await user.type(screen.getByLabelText("Secondary API key"), "sk-openai-secret");
    await user.click(screen.getByRole("button", { name: /save/i }));
    await waitFor(() => expect(calls.some((c) => c.method === "PUT")).toBe(true));
    const put = calls.find((c) => c.method === "PUT")!;
    const sent = put.body as {
      secondary_provider: string;
      secondary_model_name: string;
      secondary_api_key: string;
    };
    expect(sent.secondary_provider).toBe("openai");
    expect(sent.secondary_model_name).toBe("gpt-4o");
    expect(sent.secondary_api_key).toBe("sk-openai-secret");
  });

  it("PUTs null secondary fields when the user disables failover after it was on", async () => {
    const calls = mockFetch({
      get: () => ({
        config: mkCfg({
          secondary_provider: "openai",
          secondary_model_name: "gpt-4o",
          secondary_api_key_masked: "sk-o****9876",
          has_secondary_api_key: true,
        }),
      }),
      put: () => ({ config: mkCfg() }),
    });
    render(<LlmConfigForm />);
    await waitFor(() => expect(screen.queryByText("Loading…")).toBeNull());
    const user = userEvent.setup();
    await user.click(screen.getByLabelText("Enable failover"));
    await user.click(screen.getByRole("button", { name: /save/i }));
    await waitFor(() => expect(calls.some((c) => c.method === "PUT")).toBe(true));
    const put = calls.find((c) => c.method === "PUT")!;
    const sent = put.body as {
      secondary_provider: unknown;
      secondary_model_name: unknown;
      secondary_api_key: unknown;
    };
    expect(sent.secondary_provider).toBeNull();
    expect(sent.secondary_model_name).toBeNull();
    expect(sent.secondary_api_key).toBeNull();
  });
});
