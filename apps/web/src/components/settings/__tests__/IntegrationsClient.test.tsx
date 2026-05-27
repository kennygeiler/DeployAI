import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { KillSwitchState, TenantMcpConfigRead } from "@/lib/internal/mcp-configs-cp";

import { IntegrationsClient } from "../IntegrationsClient";

const TENANT_ID = "11111111-1111-1111-1111-111111111111";

function mkConfig(overrides: Partial<TenantMcpConfigRead> = {}): TenantMcpConfigRead {
  return {
    id: "cfg-1",
    tenant_id: TENANT_ID,
    name: "Acme Slack",
    connector_kind: "slack",
    transport: "http_sse",
    endpoint: "https://slack-mcp.example.com/sse",
    has_auth_token: false,
    allowed_tools: ["search_messages"],
    enabled: true,
    created_at: "2026-05-26T12:00:00Z",
    updated_at: "2026-05-26T12:00:00Z",
    ...overrides,
  };
}

type Call = { url: string; method: string; body?: unknown };

function mockFetch(routes: {
  list?: (callIndex: number) => { configs: TenantMcpConfigRead[] };
  create?: (body: unknown) => TenantMcpConfigRead;
  killswitchPost?: (body: { disabled: boolean }) => KillSwitchState;
}): { calls: Call[] } {
  const calls: Call[] = [];
  let listIdx = 0;
  const fetchMock = vi.fn((url: string, init?: { method?: string; body?: string }) => {
    const method = init?.method ?? "GET";
    const parsed = init?.body ? JSON.parse(init.body) : undefined;
    calls.push({ url, method, body: parsed });
    if (method === "GET" && url.includes("/mcp_configs") && !url.includes("oauth")) {
      const resp = routes.list ? routes.list(listIdx++) : { configs: [] as TenantMcpConfigRead[] };
      return Promise.resolve({ ok: true, json: () => Promise.resolve(resp) });
    }
    if (method === "POST" && url.endsWith("/mcp_configs")) {
      const cfg = routes.create
        ? routes.create(parsed)
        : mkConfig({ id: "new", name: (parsed as { name: string }).name });
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve({ config: cfg }),
      });
    }
    if (method === "POST" && url.endsWith("/mcp_killswitch")) {
      const resp = routes.killswitchPost
        ? routes.killswitchPost(parsed as { disabled: boolean })
        : ({ disabled: (parsed as { disabled: boolean }).disabled } as KillSwitchState);
      return Promise.resolve({ ok: true, json: () => Promise.resolve(resp) });
    }
    return Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
  });
  vi.stubGlobal("fetch", fetchMock);
  return { calls };
}

describe("IntegrationsClient", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("renders the empty state when no configs are present", () => {
    mockFetch({});
    render(
      <IntegrationsClient
        tenantId={TENANT_ID}
        initialConfigs={[]}
        initialKillSwitch={{ disabled: false }}
      />,
    );
    expect(screen.getByTestId("configs-empty")).toBeTruthy();
    // Catalog still renders all 5 connector kinds.
    const catalog = screen.getByTestId("connector-catalog");
    for (const label of ["Slack", "Linear", "Google Drive", "Notion", "GitHub"]) {
      expect(within(catalog).getByText(label)).toBeTruthy();
    }
    expect(screen.getByTestId("killswitch-state").textContent).toBe("OFF");
  });

  it("renders an existing config row with has_auth_token indicator and Connect button when missing", () => {
    mockFetch({});
    const cfg = mkConfig({ has_auth_token: false });
    render(
      <IntegrationsClient
        tenantId={TENANT_ID}
        initialConfigs={[cfg]}
        initialKillSwitch={{ disabled: false }}
      />,
    );
    expect(screen.getByTestId(`config-row-${cfg.id}-auth`).textContent).toContain("missing");
    expect(screen.getByTestId(`connect-slack-${cfg.id}`)).toBeTruthy();
  });

  it("hides Connect-with-Slack when the token is already present", () => {
    mockFetch({});
    const cfg = mkConfig({ has_auth_token: true });
    render(
      <IntegrationsClient
        tenantId={TENANT_ID}
        initialConfigs={[cfg]}
        initialKillSwitch={{ disabled: false }}
      />,
    );
    expect(screen.getByTestId(`config-row-${cfg.id}-auth`).textContent).toContain("token set");
    expect(screen.queryByTestId(`connect-slack-${cfg.id}`)).toBeNull();
  });

  it("opens the add modal and validates name + https endpoint before submit", async () => {
    const { calls } = mockFetch({});
    render(
      <IntegrationsClient
        tenantId={TENANT_ID}
        initialConfigs={[]}
        initialKillSwitch={{ disabled: false }}
      />,
    );
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: /add integration/i }));

    const nameInput = await screen.findByLabelText(/^Name$/);
    const endpointInput = await screen.findByLabelText(/^Endpoint/);

    // Empty form: submit disabled
    const submit = screen.getByRole("button", { name: /^create$/i });
    expect(submit).toHaveProperty("disabled", true);

    // Type a non-https endpoint: still disabled, validation message shown
    await user.type(nameInput, "My Linear");
    await user.type(endpointInput, "http://insecure.example.com/sse");
    expect(screen.getByText(/must be a valid https/i)).toBeTruthy();
    expect(submit).toHaveProperty("disabled", true);

    // Fix endpoint -> enabled, submits
    await user.clear(endpointInput);
    await user.type(endpointInput, "https://linear-mcp.example.com/sse");
    expect(submit).toHaveProperty("disabled", false);
    await user.click(submit);

    await waitFor(() => {
      expect(calls.some((c) => c.method === "POST" && c.url.endsWith("/mcp_configs"))).toBe(true);
    });
    const post = calls.find((c) => c.method === "POST" && c.url.endsWith("/mcp_configs"))!;
    const body = post.body as { name: string; endpoint: string; connector_kind: string };
    expect(body.name).toBe("My Linear");
    expect(body.endpoint).toBe("https://linear-mcp.example.com/sse");
    expect(body.connector_kind).toBe("slack"); // default in form, the catalog default
  });

  it("kill-switch ON requires confirmation modal, then POSTs disabled=true", async () => {
    const { calls } = mockFetch({});
    render(
      <IntegrationsClient
        tenantId={TENANT_ID}
        initialConfigs={[]}
        initialKillSwitch={{ disabled: false }}
      />,
    );
    const user = userEvent.setup();
    await user.click(screen.getByTestId("killswitch-on"));

    // Confirm dialog opens; clicking confirm fires the POST.
    const confirm = await screen.findByTestId("killswitch-confirm");
    await user.click(confirm);

    await waitFor(() => {
      expect(calls.some((c) => c.method === "POST" && c.url.endsWith("/mcp_killswitch"))).toBe(
        true,
      );
    });
    const post = calls.find((c) => c.method === "POST" && c.url.endsWith("/mcp_killswitch"))!;
    expect((post.body as { disabled: boolean }).disabled).toBe(true);

    // Header copy switches to the warning state.
    await waitFor(() => {
      expect(screen.getByTestId("killswitch-state").textContent).toBe("ON");
    });
    expect(screen.getByTestId("killswitch-warning")).toBeTruthy();
  });

  it("kill-switch OFF (already ON) flips back without a confirmation modal", async () => {
    const { calls } = mockFetch({
      killswitchPost: ({ disabled }) => ({ disabled }),
    });
    render(
      <IntegrationsClient
        tenantId={TENANT_ID}
        initialConfigs={[]}
        initialKillSwitch={{ disabled: true }}
      />,
    );
    const user = userEvent.setup();
    expect(screen.getByTestId("killswitch-state").textContent).toBe("ON");
    await user.click(screen.getByTestId("killswitch-off"));
    await waitFor(() => {
      expect(calls.some((c) => c.method === "POST" && c.url.endsWith("/mcp_killswitch"))).toBe(
        true,
      );
    });
    const post = calls.find((c) => c.method === "POST" && c.url.endsWith("/mcp_killswitch"))!;
    expect((post.body as { disabled: boolean }).disabled).toBe(false);
  });
});
