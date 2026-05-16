import { type NextRequest, NextResponse } from "next/server";

import { decideSync } from "@deployai/authz";

import { getActorFromHeaders } from "@/lib/internal/actor";
import { nextResponseFromStrategistCpFetchError } from "@/lib/internal/strategist-bff-cp-error";
import { strategistQueueBffCpMisconfiguredResponse } from "@/lib/internal/strategist-queues-route-guard";
import {
  cpListSolidificationQueue,
  cpPatchSolidificationQueueItem,
} from "@/lib/internal/strategist-queues-cp";

type PostBody =
  | { op: "promote"; id: string }
  | { op: "demote"; id: string; reason: string }
  | { op: "defer"; id: string };

function isRecord(x: unknown): x is Record<string, unknown> {
  return typeof x === "object" && x !== null;
}

/** Epic 9.7 — solidification queue via control-plane Postgres. */
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
    const items = await cpListSolidificationQueue(tid);
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
  const tid = actor.tenantId!.trim();

  if (body.op === "promote") {
    try {
      const row = await cpPatchSolidificationQueueItem(tid, body.id, "resolved");
      return NextResponse.json({ item: row, source: "cp" });
    } catch (e) {
      return nextResponseFromStrategistCpFetchError(e);
    }
  }
  if (body.op === "demote") {
    if (typeof raw.reason !== "string" || !raw.reason.trim()) {
      return NextResponse.json({ error: "reason required for demote" }, { status: 400 });
    }
    try {
      const row = await cpPatchSolidificationQueueItem(tid, body.id, "escalated");
      return NextResponse.json({ item: row, source: "cp" });
    } catch (e) {
      return nextResponseFromStrategistCpFetchError(e);
    }
  }
  if (body.op === "defer") {
    try {
      const row = await cpPatchSolidificationQueueItem(tid, body.id, "in-review");
      return NextResponse.json({ item: row, source: "cp" });
    } catch (e) {
      return nextResponseFromStrategistCpFetchError(e);
    }
  }
  return NextResponse.json({ error: "unknown op" }, { status: 400 });
}
