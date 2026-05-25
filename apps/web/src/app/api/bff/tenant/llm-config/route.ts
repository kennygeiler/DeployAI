import { NextResponse } from "next/server";

import { decideSync } from "@deployai/authz";

import { getActorFromHeaders, getActorIdFromHeaders } from "@/lib/internal/actor";
import { emitTenantAuditEventBackground } from "@/lib/internal/audit-emit";
import {
  cpGetTenantLlmConfig,
  cpPutTenantLlmConfig,
  type TenantLlmConfigWrite,
} from "@/lib/internal/llm-config-cp";
import { nextResponseFromStrategistCpFetchError } from "@/lib/internal/strategist-bff-cp-error";
import { strategistQueueBffCpMisconfiguredResponse } from "@/lib/internal/strategist-queues-route-guard";

/**
 * Sprint 1 — per-tenant LLM provider config UI.
 *
 * Self-hosted single-team deployments let any tenant member view / update
 * provider + model + API key (no separate admin role for v1). When we add
 * `customer_admin`-only gating in Sprint 3 (alongside per-team prompt
 * overrides), swap the action below for an admin-tier one.
 *
 * The CP response strips raw keys before they reach the browser
 * (api_key_masked + has_api_key). The PUT accepts an optional api_key —
 * omitting it preserves the previously stored secret.
 */

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

export async function GET() {
  const g = await guard();
  if ("error" in g) return g.error;
  try {
    const cfg = await cpGetTenantLlmConfig(g.tid);
    return NextResponse.json({ config: cfg }, { status: 200 });
  } catch (e) {
    return nextResponseFromStrategistCpFetchError(e);
  }
}

export async function PUT(req: Request) {
  const g = await guard();
  if ("error" in g) return g.error;
  let body: TenantLlmConfigWrite;
  try {
    body = (await req.json()) as TenantLlmConfigWrite;
  } catch {
    return new NextResponse("Bad Request: invalid JSON", { status: 400 });
  }
  if (!body || typeof body.provider !== "string" || !body.provider.trim()) {
    return new NextResponse("Bad Request: provider is required", { status: 400 });
  }
  try {
    const cfg = await cpPutTenantLlmConfig(g.tid, {
      provider: body.provider,
      model_name: body.model_name ?? null,
      // omit api_key entirely when caller didn't set one — CP preserves the prior key
      ...(body.api_key !== undefined && body.api_key !== null && body.api_key !== ""
        ? { api_key: body.api_key }
        : {}),
    });
    emitTenantAuditEventBackground(
      g.tid,
      await getActorIdFromHeaders(),
      "tenant.llm_config.updated",
      `updated tenant LLM config (${body.provider})`,
      { provider: body.provider, model_name: body.model_name ?? null },
    );
    return NextResponse.json({ config: cfg }, { status: 200 });
  } catch (e) {
    return nextResponseFromStrategistCpFetchError(e);
  }
}
