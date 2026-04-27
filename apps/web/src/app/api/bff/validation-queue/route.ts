import { type NextRequest, NextResponse } from "next/server";

import { decideSync } from "@deployai/authz";

import { listValidationQueue, patchValidationRow } from "@/lib/bff/strategist-queues-store";
import { getActorFromHeaders } from "@/lib/internal/actor";

type PostBody =
  | { op: "confirm"; id: string }
  | { op: "modify"; id: string; reason: string }
  | { op: "reject"; id: string; reason: string }
  | { op: "defer"; id: string };

function isRecord(x: unknown): x is Record<string, unknown> {
  return typeof x === "object" && x !== null;
}

/** Epic 9.6 — User Validation Queue (BFF mock). */
export async function GET() {
  const actor = await getActorFromHeaders();
  if (!actor) {
    return new NextResponse("Unauthorized", { status: 401 });
  }
  const d = decideSync(actor, "canonical:read", { kind: "canonical_memory" });
  if (!d.allow) {
    return new NextResponse("Forbidden", { status: 403 });
  }
  return NextResponse.json({ items: listValidationQueue(actor.tenantId ?? null) }, { status: 200 });
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
    const raw: unknown = await request.json();
    if (!isRecord(raw) || typeof raw.op !== "string" || typeof raw.id !== "string") {
      return NextResponse.json({ error: "invalid body" }, { status: 400 });
    }
    body = raw as PostBody;
  } catch {
    return NextResponse.json({ error: "invalid json" }, { status: 400 });
  }
  if (body.op === "confirm") {
    const row = patchValidationRow(actor.tenantId ?? null, body.id, "resolved");
    return row
      ? NextResponse.json({ item: row })
      : NextResponse.json({ error: "not found" }, { status: 404 });
  }
  if (body.op === "defer") {
    const row = patchValidationRow(actor.tenantId ?? null, body.id, "escalated");
    return row
      ? NextResponse.json({ item: row })
      : NextResponse.json({ error: "not found" }, { status: 404 });
  }
  if (body.op === "modify" || body.op === "reject") {
    if (!body.reason?.trim()) {
      return NextResponse.json({ error: "reason required" }, { status: 400 });
    }
    const row = patchValidationRow(actor.tenantId ?? null, body.id, "resolved");
    return row
      ? NextResponse.json({ item: row })
      : NextResponse.json({ error: "not found" }, { status: 404 });
  }
  return NextResponse.json({ error: "unknown op" }, { status: 400 });
}
