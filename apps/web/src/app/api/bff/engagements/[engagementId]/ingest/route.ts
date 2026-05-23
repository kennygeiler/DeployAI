import { type NextRequest, NextResponse } from "next/server";

import { decideSync } from "@deployai/authz";

import { getActorFromHeaders } from "@/lib/internal/actor";
import { cpIngestInteraction } from "@/lib/internal/ingest-cp";
import { cpExtractMatrixProposals } from "@/lib/internal/matrix-cp";
import { nextResponseFromStrategistCpFetchError } from "@/lib/internal/strategist-bff-cp-error";
import { strategistQueueBffCpMisconfiguredResponse } from "@/lib/internal/strategist-queues-route-guard";

type Ctx = { params: Promise<{ engagementId: string }> };

/**
 * Phase 6 — universal one-shot interaction import. POST lands one
 * interaction (email / meeting note / field note / manual paste) as a
 * canonical_memory_events row on the engagement. Phase 6.2 layers an
 * extraction agent that reads these events and proposes matrix entities.
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
    dedup_key?: unknown;
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
  // Default occurred_at to "now" — one-shot imports are typically captured
  // close to when the interaction happened; the caller can override.
  const occurredAt =
    typeof parsed.occurred_at === "string" && parsed.occurred_at.trim()
      ? parsed.occurred_at.trim()
      : new Date().toISOString();
  const sourceRef =
    typeof parsed.source_ref === "string" && parsed.source_ref.trim()
      ? parsed.source_ref.trim()
      : null;
  const dedupKey =
    typeof parsed.dedup_key === "string" && parsed.dedup_key.trim()
      ? parsed.dedup_key.trim()
      : null;
  let event: Awaited<ReturnType<typeof cpIngestInteraction>>;
  try {
    event = await cpIngestInteraction(tid, engagementId, {
      source,
      occurred_at: occurredAt,
      content,
      source_ref: sourceRef,
      dedup_key: dedupKey,
    });
  } catch (e) {
    return nextResponseFromStrategistCpFetchError(e);
  }
  // Phase 6.2c — chain Cartographer extraction on the new event. Best-effort:
  // failure here MUST NOT fail the ingest (the event is real; the agent is
  // recoverable). Detail page refreshes the aggregate to surface any new
  // proposals via the 6.2a review section.
  let extractError: string | null = null;
  try {
    await cpExtractMatrixProposals(tid, engagementId, event.id);
  } catch (e) {
    extractError = e instanceof Error ? e.message : String(e);
    console.warn(
      `bff/ingest: matrix extraction failed for event ${event.id} (engagement ${engagementId}):`,
      extractError,
    );
  }
  return NextResponse.json({ event, extract_error: extractError, source: "cp" }, { status: 201 });
}
