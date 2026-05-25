import { type NextRequest, NextResponse } from "next/server";

import { decideSync } from "@deployai/authz";

import { getActorFromHeaders } from "@/lib/internal/actor";
import { ALLOWED_SOURCE_KINDS, cpFetchChain } from "@/lib/internal/ledger-cp";
import { nextResponseFromStrategistCpFetchError } from "@/lib/internal/strategist-bff-cp-error";
import { strategistQueueBffCpMisconfiguredResponse } from "@/lib/internal/strategist-queues-route-guard";

type Ctx = { params: Promise<{ engagementId: string; eventId: string }> };

const DEFAULT_DEPTH = 3;
const MAX_DEPTH = 10;
const ALLOWED_DIRECTIONS = new Set(["backward", "forward", "both"]);

function parseDepth(raw: string | null): number | { error: NextResponse } {
  if (raw === null) return DEFAULT_DEPTH;
  const parsed = Number(raw);
  if (!Number.isFinite(parsed) || !Number.isInteger(parsed) || parsed < 1 || parsed > MAX_DEPTH) {
    return { error: NextResponse.json({ error: "invalid max_depth" }, { status: 400 }) };
  }
  return parsed;
}

export async function GET(request: NextRequest, ctx: Ctx) {
  const actor = await getActorFromHeaders();
  if (!actor) {
    return new NextResponse("Unauthorized", { status: 401 });
  }
  const d = decideSync(actor, "canonical:read", { kind: "canonical_memory" });
  if (!d.allow) {
    return new NextResponse("Forbidden", { status: 403 });
  }
  const cpMisconfigured = strategistQueueBffCpMisconfiguredResponse(actor.tenantId);
  if (cpMisconfigured) {
    return cpMisconfigured;
  }
  const { engagementId, eventId } = await ctx.params;
  const tid = actor.tenantId!.trim();
  const sp = new URL(request.url).searchParams;

  const depth = parseDepth(sp.get("max_depth"));
  if (typeof depth === "object") return depth.error;
  const directionRaw = sp.get("direction");
  if (directionRaw !== null && !ALLOWED_DIRECTIONS.has(directionRaw)) {
    return NextResponse.json({ error: "invalid direction" }, { status: 400 });
  }

  try {
    const body = await cpFetchChain(tid, engagementId, eventId, {
      max_depth: depth,
      ...(directionRaw ? { direction: directionRaw as "backward" | "forward" | "both" } : {}),
    });
    const invalid = body.nodes.map((n) => n.sourceKind).filter((k) => !ALLOWED_SOURCE_KINDS.has(k));
    if (invalid.length > 0) {
      return NextResponse.json(
        { error: `unknown source_kind value(s): ${Array.from(new Set(invalid)).join(", ")}` },
        { status: 422 },
      );
    }
    return NextResponse.json({ ...body, source: "cp" }, { status: 200 });
  } catch (e) {
    return nextResponseFromStrategistCpFetchError(e);
  }
}
