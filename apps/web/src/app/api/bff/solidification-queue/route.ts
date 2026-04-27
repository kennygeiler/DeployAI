import { type NextRequest, NextResponse } from "next/server";

import { decideSync } from "@deployai/authz";

import { listSolidificationQueue, patchSolidificationRow } from "@/lib/bff/strategist-queues-store";
import { getActorFromHeaders } from "@/lib/internal/actor";

type PostBody =
  | { op: "promote"; id: string }
  | { op: "demote"; id: string; reason?: string }
  | { op: "defer"; id: string };

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
  let body: PostBody;
  try {
    body = (await request.json()) as PostBody;
  } catch {
    return NextResponse.json({ error: "invalid json" }, { status: 400 });
  }
  if (body.op === "promote") {
    const row = patchSolidificationRow(actor.tenantId ?? null, body.id, "resolved");
    return row
      ? NextResponse.json({ item: row })
      : NextResponse.json({ error: "not found" }, { status: 404 });
  }
  if (body.op === "demote") {
    const row = patchSolidificationRow(actor.tenantId ?? null, body.id, "escalated");
    return row
      ? NextResponse.json({ item: row })
      : NextResponse.json({ error: "not found" }, { status: 404 });
  }
  if (body.op === "defer") {
    const row = patchSolidificationRow(actor.tenantId ?? null, body.id, "in-review");
    return row
      ? NextResponse.json({ item: row })
      : NextResponse.json({ error: "not found" }, { status: 404 });
  }
  return NextResponse.json({ error: "unknown op" }, { status: 400 });
}
