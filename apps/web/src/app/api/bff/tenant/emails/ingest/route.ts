import { NextResponse } from "next/server";

import { decideSync } from "@deployai/authz";

import { getActorFromHeaders } from "@/lib/internal/actor";
import { cpIngestEmailPaste, zEmailPasteBody } from "@/lib/internal/emails-cp";
import { nextResponseFromStrategistCpFetchError } from "@/lib/internal/strategist-bff-cp-error";
import { strategistQueueBffCpMisconfiguredResponse } from "@/lib/internal/strategist-queues-route-guard";

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

export async function POST(req: Request) {
  const g = await guard();
  if ("error" in g) return g.error;
  const raw: unknown = await req.json().catch(() => null);
  const parsed = zEmailPasteBody.safeParse(raw);
  if (!parsed.success) {
    return new NextResponse("Bad Request: source and raw are required", { status: 400 });
  }
  try {
    const events = await cpIngestEmailPaste(g.tid, parsed.data);
    return NextResponse.json({ events }, { status: 201 });
  } catch (e) {
    return nextResponseFromStrategistCpFetchError(e);
  }
}
