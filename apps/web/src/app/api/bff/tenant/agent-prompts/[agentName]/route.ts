import { NextResponse } from "next/server";

import { decideSync } from "@deployai/authz";

import { getActorFromHeaders } from "@/lib/internal/actor";
import {
  AGENT_NAMES,
  type AgentName,
  cpDeleteTenantAgentPrompt,
  cpPutTenantAgentPrompt,
} from "@/lib/internal/agent-prompts-cp";
import { nextResponseFromStrategistCpFetchError } from "@/lib/internal/strategist-bff-cp-error";
import { strategistQueueBffCpMisconfiguredResponse } from "@/lib/internal/strategist-queues-route-guard";

async function guard() {
  const actor = await getActorFromHeaders();
  if (!actor) {
    return { error: new NextResponse("Unauthorized", { status: 401 }) } as const;
  }
  const d = decideSync(actor, "canonical:read", { kind: "canonical_memory" });
  if (!d.allow) {
    return { error: new NextResponse("Forbidden", { status: 403 }) } as const;
  }
  const cpMisconfigured = strategistQueueBffCpMisconfiguredResponse(actor.tenantId);
  if (cpMisconfigured) {
    return { error: cpMisconfigured } as const;
  }
  return { tid: actor.tenantId!.trim() } as const;
}

function parseAgentName(raw: string): AgentName | null {
  return (AGENT_NAMES as readonly string[]).includes(raw) ? (raw as AgentName) : null;
}

export async function PUT(req: Request, ctx: { params: Promise<{ agentName: string }> }) {
  const g = await guard();
  if ("error" in g) return g.error;
  const { agentName: rawName } = await ctx.params;
  const agentName = parseAgentName(rawName);
  if (!agentName) {
    return new NextResponse(`Bad Request: unknown agent_name: ${rawName}`, { status: 400 });
  }
  let body: { prompt_text?: unknown };
  try {
    body = (await req.json()) as { prompt_text?: unknown };
  } catch {
    return new NextResponse("Bad Request: invalid JSON", { status: 400 });
  }
  const promptText = typeof body.prompt_text === "string" ? body.prompt_text : "";
  if (!promptText.trim()) {
    return new NextResponse("Bad Request: prompt_text is required", { status: 400 });
  }
  try {
    const entry = await cpPutTenantAgentPrompt(g.tid, agentName, promptText);
    return NextResponse.json({ entry }, { status: 200 });
  } catch (e) {
    return nextResponseFromStrategistCpFetchError(e);
  }
}

export async function DELETE(_req: Request, ctx: { params: Promise<{ agentName: string }> }) {
  const g = await guard();
  if ("error" in g) return g.error;
  const { agentName: rawName } = await ctx.params;
  const agentName = parseAgentName(rawName);
  if (!agentName) {
    return new NextResponse(`Bad Request: unknown agent_name: ${rawName}`, { status: 400 });
  }
  try {
    await cpDeleteTenantAgentPrompt(g.tid, agentName);
    return new NextResponse(null, { status: 204 });
  } catch (e) {
    return nextResponseFromStrategistCpFetchError(e);
  }
}
