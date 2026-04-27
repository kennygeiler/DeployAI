import { type NextRequest, NextResponse } from "next/server";

import { decideSync } from "@deployai/authz";

import {
  listActionQueue,
  mutateActionQueueItem,
  pushActionQueueAudit,
  type ActionQueueStatus,
} from "@/lib/bff/strategist-queues-store";
import { getActorFromHeaders } from "@/lib/internal/actor";

type PostBody =
  | { op: "claim"; id: string }
  | { op: "progress"; id: string }
  | {
      op: "resolve";
      id: string;
      state: "resolved" | "deferred" | "rejected_with_reason";
      reason?: string;
      evidence_event_ids?: string[];
    };

/**
 * Epic 9.5 — Action Queue list + legacy POST body (prefer `/action-queue/:id/{claim,progress,resolve}`).
 */
export async function GET() {
  const actor = await getActorFromHeaders();
  if (!actor) {
    return new NextResponse("Unauthorized", { status: 401 });
  }
  const d = decideSync(actor, "canonical:read", { kind: "canonical_memory" });
  if (!d.allow) {
    return new NextResponse("Forbidden", { status: 403 });
  }
  return NextResponse.json({ items: listActionQueue(actor.tenantId ?? null) }, { status: 200 });
}

export async function POST(request: NextRequest) {
  const actor = await getActorFromHeaders();
  if (!actor) {
    return new NextResponse("Unauthorized", { status: 401 });
  }
  const d = decideSync(actor, "canonical:read", { kind: "canonical_memory" });
  if (!d.allow) {
    return new NextResponse("Forbidden", { status: 403 });
  }
  let body: PostBody;
  try {
    body = (await request.json()) as PostBody;
  } catch {
    return NextResponse.json({ error: "invalid json" }, { status: 400 });
  }
  const who = actor.role === "deployment_strategist" ? "you" : actor.role;
  if (body.op === "claim") {
    const next = mutateActionQueueItem(actor.tenantId ?? null, body.id, {
      status: "claimed",
      claimed_by: who,
    });
    if (next) {
      pushActionQueueAudit(actor.tenantId ?? null, "action_queue.claimed", {
        itemId: body.id,
        claimed_by: who,
      });
    }
    return next
      ? NextResponse.json({ item: next })
      : NextResponse.json({ error: "not found" }, { status: 404 });
  }
  if (body.op === "progress") {
    const next = mutateActionQueueItem(actor.tenantId ?? null, body.id, {
      status: "in_progress",
      claimed_by: who,
    });
    if (next) {
      pushActionQueueAudit(actor.tenantId ?? null, "action_queue.in_progress", {
        itemId: body.id,
        claimed_by: who,
      });
    }
    return next
      ? NextResponse.json({ item: next })
      : NextResponse.json({ error: "not found" }, { status: 404 });
  }
  if (body.op === "resolve") {
    const st = body.state as ActionQueueStatus;
    const allowed: ActionQueueStatus[] = ["resolved", "deferred", "rejected_with_reason"];
    if (!allowed.includes(st)) {
      return NextResponse.json({ error: "invalid resolve state" }, { status: 400 });
    }
    if (st === "rejected_with_reason" && !(body.reason && body.reason.trim())) {
      return NextResponse.json(
        { error: "reason required for rejected_with_reason" },
        { status: 400 },
      );
    }
    const evidenceIds = Array.isArray(body.evidence_event_ids)
      ? body.evidence_event_ids.filter((x) => typeof x === "string" && x.length > 0)
      : undefined;
    const next = mutateActionQueueItem(actor.tenantId ?? null, body.id, {
      status: st,
      claimed_by: who,
      resolution_reason: body.reason?.trim() || null,
      evidence_event_ids: evidenceIds && evidenceIds.length > 0 ? evidenceIds : null,
    });
    if (next) {
      pushActionQueueAudit(actor.tenantId ?? null, "action_queue.resolved", {
        itemId: body.id,
        state: body.state,
        reason: body.reason?.trim() ?? null,
        evidence_event_ids: evidenceIds ?? null,
      });
    }
    return next
      ? NextResponse.json({ item: next })
      : NextResponse.json({ error: "not found" }, { status: 404 });
  }
  return NextResponse.json({ error: "unknown op" }, { status: 400 });
}
