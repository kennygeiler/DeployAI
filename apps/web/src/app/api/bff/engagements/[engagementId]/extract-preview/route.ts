import { type NextRequest, NextResponse } from "next/server";

import { decideSync } from "@deployai/authz";

import { getActorFromHeaders } from "@/lib/internal/actor";
import { cpExtractPreview } from "@/lib/internal/extract-preview-cp";
import { nextResponseFromStrategistCpFetchError } from "@/lib/internal/strategist-bff-cp-error";
import { strategistQueueBffCpMisconfiguredResponse } from "@/lib/internal/strategist-queues-route-guard";

type Ctx = { params: Promise<{ engagementId: string }> };

/**
 * Sprint 2.2 — paste preview. Runs the matrix-extraction agent on a
 * candidate interaction without persisting anything. Commit goes through
 * the existing /ingest BFF (which chains /extract).
 */
export async function POST(request: NextRequest, ctx: Ctx) {
  const actor = await getActorFromHeaders();
  if (!actor) {
    return new NextResponse("Unauthorized", { status: 401 });
  }
  const d = decideSync(actor, "canonical:read", { kind: "canonical_memory" });
  if (!d.allow) {
    return new NextResponse("Forbidden", { status: 403 });
  }
  const cpMisconfigured = strategistQueueBffCpMisconfiguredResponse(actor.tenantId);
  if (cpMisconfigured) {
    return cpMisconfigured;
  }
  const { engagementId } = await ctx.params;
  const tid = actor.tenantId!.trim();
  let parsed: {
    source?: unknown;
    occurred_at?: unknown;
    content?: unknown;
    source_ref?: unknown;
  };
  try {
    parsed = (await request.json()) as typeof parsed;
  } catch {
    return NextResponse.json({ error: "invalid json" }, { status: 400 });
  }
  const source = typeof parsed.source === "string" ? parsed.source.trim() : "";
  if (!source) {
    return NextResponse.json({ error: "source is required" }, { status: 400 });
  }
  const content =
    parsed.content && typeof parsed.content === "object" && !Array.isArray(parsed.content)
      ? (parsed.content as Record<string, unknown>)
      : null;
  if (!content) {
    return NextResponse.json({ error: "content must be a JSON object" }, { status: 400 });
  }
  const occurredAt =
    typeof parsed.occurred_at === "string" && parsed.occurred_at.trim()
      ? parsed.occurred_at.trim()
      : new Date().toISOString();
  const sourceRef =
    typeof parsed.source_ref === "string" && parsed.source_ref.trim()
      ? parsed.source_ref.trim()
      : null;
  try {
    const preview = await cpExtractPreview(tid, engagementId, {
      source,
      occurred_at: occurredAt,
      content,
      source_ref: sourceRef,
    });
    return NextResponse.json({ ...preview, source: "cp" }, { status: 200 });
  } catch (e) {
    return nextResponseFromStrategistCpFetchError(e);
  }
}
