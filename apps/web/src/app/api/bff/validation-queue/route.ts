import { type NextRequest, NextResponse } from "next/server";

import { decideSync } from "@deployai/authz";

import { getActorFromHeaders } from "@/lib/internal/actor";
import { nextResponseFromStrategistCpFetchError } from "@/lib/internal/strategist-bff-cp-error";
import { strategistQueueBffCpMisconfiguredResponse } from "@/lib/internal/strategist-queues-route-guard";
import {
  cpListValidationQueue,
  cpPatchValidationQueueItem,
} from "@/lib/internal/strategist-queues-cp";

type PostBody =
  | { op: "confirm"; id: string }
  | { op: "modify"; id: string; reason: string }
  | { op: "reject"; id: string; reason: string }
  | { op: "defer"; id: string };

function isRecord(x: unknown): x is Record<string, unknown> {
  return typeof x === "object" && x !== null;
}

/** Epic 9.6 — validation queue via control-plane Postgres. */
export async function GET() {
  const actor = await getActorFromHeaders();
  if (!actor) {
    return new NextResponse("Unauthorized", { status: 401 });
  }
  const d = decideSync(actor, "canonical:read", { kind: "canonical_memory" });
  if (!d.allow) {
    return new NextResponse("Forbidden", { status: 403 });
  }
  const cpMisconfigured = strategistQueueBffCpMisconfiguredResponse(actor.tenantId);
  if (cpMisconfigured) return cpMisconfigured;
  const tid = actor.tenantId!.trim();
  try {
    const items = await cpListValidationQueue(tid);
    return NextResponse.json({ items, source: "cp" }, { status: 200 });
  } catch (e) {
    return nextResponseFromStrategistCpFetchError(e);
  }
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
  const cpMisconfigured = strategistQueueBffCpMisconfiguredResponse(actor.tenantId);
  if (cpMisconfigured) return cpMisconfigured;
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
  const tid = actor.tenantId!.trim();

  if (body.op === "confirm") {
    try {
      const row = await cpPatchValidationQueueItem(tid, body.id, "resolved");
      return NextResponse.json({ item: row, source: "cp" });
    } catch (e) {
      return nextResponseFromStrategistCpFetchError(e);
    }
  }
  if (body.op === "defer") {
    try {
      const row = await cpPatchValidationQueueItem(tid, body.id, "in-review");
      return NextResponse.json({ item: row, source: "cp" });
    } catch (e) {
      return nextResponseFromStrategistCpFetchError(e);
    }
  }
  if (body.op === "modify" || body.op === "reject") {
    if (!body.reason?.trim()) {
      return NextResponse.json({ error: "reason required" }, { status: 400 });
    }
    try {
      const row = await cpPatchValidationQueueItem(tid, body.id, "resolved");
      return NextResponse.json({ item: row, source: "cp" });
    } catch (e) {
      return nextResponseFromStrategistCpFetchError(e);
    }
  }
  return NextResponse.json({ error: "unknown op" }, { status: 400 });
}
