/**
 * Sprint 5 — per-tenant agent prompt overrides client.
 *
 * Wraps `GET /internal/v1/tenants/{tenant_id}/agent-prompts`,
 * `PUT /internal/v1/tenants/{tenant_id}/agent-prompts/{agent_name}`,
 * and `DELETE /internal/v1/tenants/{tenant_id}/agent-prompts/{agent_name}`.
 *
 * The GET always returns one entry per supported agent — value is the
 * resolved prompt (override if present, baked-in default otherwise) and
 * `is_default` tells the UI whether to show "Reset to default".
 */
import { getControlPlaneBaseUrl, getControlPlaneInternalKey } from "@/lib/internal/control-plane";

export type AgentName = "cartographer" | "oracle" | "master_strategist";

export const AGENT_NAMES: readonly AgentName[] = ["cartographer", "oracle", "master_strategist"];

export type AgentPromptEntry = {
  value: string;
  is_default: boolean;
};

export type AgentPromptsRead = {
  prompts: Record<AgentName, AgentPromptEntry>;
};

function cpHeaders(): Record<string, string> {
  const key = getControlPlaneInternalKey();
  if (!key) {
    throw new Error("DEPLOYAI_INTERNAL_API_KEY not set");
  }
  return { "X-DeployAI-Internal-Key": key };
}

function cpBase(): string {
  const base = getControlPlaneBaseUrl()?.replace(/\/$/, "");
  if (!base) {
    throw new Error("DEPLOYAI_CONTROL_PLANE_URL not set");
  }
  return base;
}

export async function cpGetTenantAgentPrompts(tenantId: string): Promise<AgentPromptsRead> {
  const url = `${cpBase()}/internal/v1/tenants/${encodeURIComponent(tenantId)}/agent-prompts`;
  const r = await fetch(url, { method: "GET", headers: cpHeaders(), cache: "no-store" });
  if (!r.ok) {
    throw new Error(`cp agent-prompts get ${r.status}: ${await r.text()}`);
  }
  return (await r.json()) as AgentPromptsRead;
}

export async function cpPutTenantAgentPrompt(
  tenantId: string,
  agentName: AgentName,
  promptText: string,
): Promise<AgentPromptEntry> {
  const url = `${cpBase()}/internal/v1/tenants/${encodeURIComponent(tenantId)}/agent-prompts/${encodeURIComponent(agentName)}`;
  const r = await fetch(url, {
    method: "PUT",
    headers: { ...cpHeaders(), "Content-Type": "application/json" },
    body: JSON.stringify({ prompt_text: promptText }),
    cache: "no-store",
  });
  if (!r.ok) {
    throw new Error(`cp agent-prompts put ${r.status}: ${await r.text()}`);
  }
  return (await r.json()) as AgentPromptEntry;
}

export async function cpDeleteTenantAgentPrompt(
  tenantId: string,
  agentName: AgentName,
): Promise<void> {
  const url = `${cpBase()}/internal/v1/tenants/${encodeURIComponent(tenantId)}/agent-prompts/${encodeURIComponent(agentName)}`;
  const r = await fetch(url, { method: "DELETE", headers: cpHeaders(), cache: "no-store" });
  if (!r.ok && r.status !== 204) {
    throw new Error(`cp agent-prompts delete ${r.status}: ${await r.text()}`);
  }
}
