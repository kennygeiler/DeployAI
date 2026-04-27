import { type NextRequest, NextResponse } from "next/server";

import { decideSync } from "@deployai/authz";

import {
  listSolidificationQueue,
  patchSolidificationRow,
  pushSolidificationAudit,
} from "@/lib/bff/strategist-queues-store";
import { getActorFromHeaders } from "@/lib/internal/actor";

type PostBody =
  | { op: "promote"; id: string }
  | { op: "demote"; id: string; reason: string }
  | { op: "defer"; id: string };

function isRecord(x: unknown): x is Record<string, unknown> {
  return typeof x === "object" && x !== null;
}

/** Epic 9.7 — Solidification review queue (BFF mock). */
export async function GET() {
  const actor = await getActorFromHeaders();
  if (!actor) {
    return new NextResponse("Unauthorized", { status: 401 });
  }
  const d = decideSync(actor, "canonical:read", { kind: "canonical_memory" });
  if (!d.allow) {
    return new NextResponse("Forbidden", { status: 403 });
  }
  return NextResponse.json(
    { items: listSolidificationQueue(actor.tenantId ?? null) },
    { status: 200 },
  );
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
  let raw: unknown;
  try {
    raw = await request.json();
  } catch {
    return NextResponse.json({ error: "invalid json" }, { status: 400 });
  }
  if (!isRecord(raw) || typeof raw.op !== "string" || typeof raw.id !== "string") {
    return NextResponse.json({ error: "op and id required" }, { status: 400 });
  }
  const body = raw as PostBody;
  if (body.op === "promote") {
    pushSolidificationAudit(actor.tenantId ?? null, "solidification.promoted", { id: body.id });
    const row = patchSolidificationRow(actor.tenantId ?? null, body.id, "resolved");
    return row
      ? NextResponse.json({ item: row })
      : NextResponse.json({ error: "not found" }, { status: 404 });
  }
  if (body.op === "demote") {
    if (typeof raw.reason !== "string" || !raw.reason.trim()) {
      return NextResponse.json({ error: "reason required for demote" }, { status: 400 });
    }
    pushSolidificationAudit(actor.tenantId ?? null, "solidification.demoted", {
      id: body.id,
      reason: raw.reason.trim(),
    });
    const row = patchSolidificationRow(actor.tenantId ?? null, body.id, "escalated");
    return row
      ? NextResponse.json({ item: row })
      : NextResponse.json({ error: "not found" }, { status: 404 });
  }
  if (body.op === "defer") {
    pushSolidificationAudit(actor.tenantId ?? null, "solidification.deferred", { id: body.id });
    const row = patchSolidificationRow(actor.tenantId ?? null, body.id, "in-review");
    return row
      ? NextResponse.json({ item: row })
      : NextResponse.json({ error: "not found" }, { status: 404 });
  }
  return NextResponse.json({ error: "unknown op" }, { status: 400 });
}
