import { type NextRequest, NextResponse } from "next/server";

import { decideSync } from "@deployai/authz";

import {
  listActionQueue,
  mutateActionQueueItem,
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
    };

/**
 * Epic 9.5 — Action Queue list + lifecycle (BFF mock until CP `action_queue_items` ships).
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
    return next
      ? NextResponse.json({ item: next })
      : NextResponse.json({ error: "not found" }, { status: 404 });
  }
  if (body.op === "progress") {
    const next = mutateActionQueueItem(actor.tenantId ?? null, body.id, {
      status: "in_progress",
      claimed_by: who,
    });
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
    const next = mutateActionQueueItem(actor.tenantId ?? null, body.id, {
      status: st,
      claimed_by: who,
    });
    return next
      ? NextResponse.json({ item: next })
      : NextResponse.json({ error: "not found" }, { status: 404 });
  }
  return NextResponse.json({ error: "unknown op" }, { status: 400 });
}
