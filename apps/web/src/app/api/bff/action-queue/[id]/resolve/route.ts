import { decideSync } from "@deployai/authz";
import { type NextRequest, NextResponse } from "next/server";

import {
  mutateActionQueueItem,
  pushActionQueueAudit,
  type ActionQueueStatus,
} from "@/lib/bff/strategist-queues-store";
import { getActorFromHeaders, getActorIdFromHeaders } from "@/lib/internal/actor";
import { postStrategistActivityToCp } from "@/lib/internal/strategist-cp-activity";

type ResolveBody = {
  state: "resolved" | "deferred" | "rejected_with_reason";
  reason?: string;
  evidence_event_ids?: string[];
};

function isRecord(x: unknown): x is Record<string, unknown> {
  return typeof x === "object" && x !== null;
}

/** Epic 9.5 — `POST /api/bff/action-queue/:id/resolve` (FR58). */
export async function POST(request: NextRequest, ctx: { params: Promise<{ id: string }> }) {
  const actor = await getActorFromHeaders();
  if (!actor) {
    return new NextResponse("Unauthorized", { status: 401 });
  }
  const d = decideSync(actor, "canonical:read", { kind: "canonical_memory" });
  if (!d.allow) {
    return new NextResponse("Forbidden", { status: 403 });
  }
  const { id } = await ctx.params;
  let body: ResolveBody;
  try {
    const raw: unknown = await request.json();
    if (!isRecord(raw) || typeof raw.state !== "string") {
      return NextResponse.json({ error: "invalid body" }, { status: 400 });
    }
    body = raw as ResolveBody;
  } catch {
    return NextResponse.json({ error: "invalid json" }, { status: 400 });
  }
  const allowed: ActionQueueStatus[] = ["resolved", "deferred", "rejected_with_reason"];
  if (!allowed.includes(body.state as ActionQueueStatus)) {
    return NextResponse.json({ error: "invalid resolve state" }, { status: 400 });
  }
  if (body.state === "rejected_with_reason" && !(body.reason && body.reason.trim())) {
    return NextResponse.json(
      { error: "reason required for rejected_with_reason" },
      { status: 400 },
    );
  }
  const who = actor.role === "deployment_strategist" ? "you" : actor.role;
  const evidenceIds = Array.isArray(body.evidence_event_ids)
    ? body.evidence_event_ids.filter((x): x is string => typeof x === "string" && x.length > 0)
    : undefined;
  const next = mutateActionQueueItem(actor.tenantId ?? null, id, {
    status: body.state as ActionQueueStatus,
    claimed_by: who,
    resolution_reason: body.reason?.trim() || null,
    evidence_event_ids: evidenceIds && evidenceIds.length > 0 ? evidenceIds : null,
  });
  if (!next) {
    return NextResponse.json({ error: "not found" }, { status: 404 });
  }
  pushActionQueueAudit(actor.tenantId ?? null, "action_queue.resolved", {
    itemId: id,
    state: body.state,
    reason: body.reason?.trim() ?? null,
    evidence_event_ids: evidenceIds ?? null,
  });
  const tid = actor.tenantId?.trim();
  const aid = await getActorIdFromHeaders();
  if (tid && aid) {
    void postStrategistActivityToCp({
      tenantId: tid,
      actorId: aid,
      category: "action_queue_resolved",
      summary: `Action queue ${body.state}: ${id.slice(0, 8)}…`,
      detail: { item_id: id, state: body.state },
      refId: null,
    });
  }
  return NextResponse.json({ item: next }, { status: 200 });
}
