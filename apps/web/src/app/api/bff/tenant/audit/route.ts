import { NextResponse } from "next/server";

import { decideSync } from "@deployai/authz";

import { getActorFromHeaders } from "@/lib/internal/actor";
import { cpListAuditEvents, type AuditListOpts } from "@/lib/internal/audit-cp";
import { nextResponseFromStrategistCpFetchError } from "@/lib/internal/strategist-bff-cp-error";
import { strategistQueueBffCpMisconfiguredResponse } from "@/lib/internal/strategist-queues-route-guard";

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const KIND_RE = /^[A-Za-z0-9_.:-]{1,200}$/;

async function guard() {
  const actor = await getActorFromHeaders();
  if (!actor) {
    return { error: new NextResponse("Unauthorized", { status: 401 }) } as const;
  }
  const d = decideSync(actor, "canonical:read", { kind: "canonical_memory" });
  if (!d.allow) {
    return { error: new NextResponse("Forbidden", { status: 403 }) } as const;
  }
  const cpMisconfigured = strategistQueueBffCpMisconfiguredResponse(actor.tenantId);
  if (cpMisconfigured) {
    return { error: cpMisconfigured } as const;
  }
  return { tid: actor.tenantId!.trim() } as const;
}

export async function GET(req: Request) {
  const g = await guard();
  if ("error" in g) return g.error;
  const url = new URL(req.url);
  const opts: AuditListOpts = {};

  const limitRaw = url.searchParams.get("limit");
  if (limitRaw !== null) {
    const n = Number.parseInt(limitRaw, 10);
    if (!Number.isFinite(n) || n < 1 || n > 500) {
      return new NextResponse("Bad Request: limit must be 1..500", { status: 400 });
    }
    opts.limit = n;
  }
  const before = url.searchParams.get("before");
  if (before !== null) {
    if (Number.isNaN(Date.parse(before))) {
      return new NextResponse("Bad Request: before must be ISO-8601", { status: 400 });
    }
    opts.before = before;
  }
  const actor = url.searchParams.get("actor");
  if (actor !== null) {
    if (!UUID_RE.test(actor)) {
      return new NextResponse("Bad Request: actor must be a UUID", { status: 400 });
    }
    opts.actor = actor;
  }
  const kind = url.searchParams.get("kind");
  if (kind !== null) {
    if (!KIND_RE.test(kind)) {
      return new NextResponse("Bad Request: invalid kind", { status: 400 });
    }
    opts.kind = kind;
  }

  try {
    const events = await cpListAuditEvents(g.tid, opts);
    return NextResponse.json({ events }, { status: 200 });
  } catch (e) {
    return nextResponseFromStrategistCpFetchError(e);
  }
}
