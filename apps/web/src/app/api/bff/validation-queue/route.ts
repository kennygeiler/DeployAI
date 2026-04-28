import { type NextRequest, NextResponse } from "next/server";

import { decideSync } from "@deployai/authz";

import {
  listValidationQueue,
  patchValidationRow,
  pushValidationAudit,
} from "@/lib/bff/strategist-queues-store";
import { getActorFromHeaders } from "@/lib/internal/actor";
import { getControlPlaneBaseUrl, getControlPlaneInternalKey } from "@/lib/internal/control-plane";
import { strategistQueuesUseControlPlane } from "@/lib/internal/strategist-queues-backend";
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
  const tid = actor.tenantId?.trim();
  if (
    strategistQueuesUseControlPlane() &&
    tid &&
    getControlPlaneBaseUrl() &&
    getControlPlaneInternalKey()
  ) {
    try {
      const items = await cpListValidationQueue(tid);
      return NextResponse.json({ items, source: "cp" }, { status: 200 });
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      return NextResponse.json({ error: msg, source: "cp_error" }, { status: 502 });
    }
  }
  return NextResponse.json(
    { items: listValidationQueue(actor.tenantId ?? null), source: "memory" },
    {
      status: 200,
    },
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
    const raw: unknown = await request.json();
    if (!isRecord(raw) || typeof raw.op !== "string" || typeof raw.id !== "string") {
      return NextResponse.json({ error: "invalid body" }, { status: 400 });
    }
    body = raw as PostBody;
  } catch {
    return NextResponse.json({ error: "invalid json" }, { status: 400 });
  }
  const tid = actor.tenantId?.trim();
  const useCp =
    strategistQueuesUseControlPlane() &&
    tid &&
    getControlPlaneBaseUrl() &&
    getControlPlaneInternalKey();

  if (body.op === "confirm") {
    if (useCp) {
      try {
        const row = await cpPatchValidationQueueItem(tid!, body.id, "resolved");
        return NextResponse.json({ item: row, source: "cp" });
      } catch {
        return NextResponse.json({ error: "not found" }, { status: 404 });
      }
    }
    pushValidationAudit(actor.tenantId ?? null, "validation.confirmed", { id: body.id });
    const row = patchValidationRow(actor.tenantId ?? null, body.id, "resolved");
    return row
      ? NextResponse.json({ item: row, source: "memory" })
      : NextResponse.json({ error: "not found" }, { status: 404 });
  }
  if (body.op === "defer") {
    if (useCp) {
      try {
        const row = await cpPatchValidationQueueItem(tid!, body.id, "in-review");
        return NextResponse.json({ item: row, source: "cp" });
      } catch {
        return NextResponse.json({ error: "not found" }, { status: 404 });
      }
    }
    pushValidationAudit(actor.tenantId ?? null, "validation.deferred", { id: body.id });
    const row = patchValidationRow(actor.tenantId ?? null, body.id, "in-review");
    return row
      ? NextResponse.json({ item: row, source: "memory" })
      : NextResponse.json({ error: "not found" }, { status: 404 });
  }
  if (body.op === "modify" || body.op === "reject") {
    if (!body.reason?.trim()) {
      return NextResponse.json({ error: "reason required" }, { status: 400 });
    }
    const kind = body.op === "modify" ? "validation.modified" : "validation.rejected";
    if (useCp) {
      try {
        const row = await cpPatchValidationQueueItem(tid!, body.id, "resolved");
        return NextResponse.json({ item: row, source: "cp" });
      } catch {
        return NextResponse.json({ error: "not found" }, { status: 404 });
      }
    }
    pushValidationAudit(actor.tenantId ?? null, kind, {
      id: body.id,
      reason: body.reason.trim(),
    });
    const row = patchValidationRow(actor.tenantId ?? null, body.id, "resolved");
    return row
      ? NextResponse.json({ item: row, source: "memory" })
      : NextResponse.json({ error: "not found" }, { status: 404 });
  }
  return NextResponse.json({ error: "unknown op" }, { status: 400 });
}
