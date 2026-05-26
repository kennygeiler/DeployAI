import { type NextRequest, NextResponse } from "next/server";

import { decideSync } from "@deployai/authz";

import { getActorFromHeaders } from "@/lib/internal/actor";
import { cpCreateInsightFollowup } from "@/lib/internal/insights-cp";
import { nextResponseFromStrategistCpFetchError } from "@/lib/internal/strategist-bff-cp-error";
import { strategistQueueBffCpMisconfiguredResponse } from "@/lib/internal/strategist-queues-route-guard";

type Ctx = { params: Promise<{ engagementId: string; insightId: string }> };

const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/;
const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

type FollowupBody = { owner_user_id: string; due_date: string };

export async function POST(request: NextRequest, ctx: Ctx) {
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
  const { engagementId, insightId } = await ctx.params;
  const tid = actor.tenantId!.trim();
  let raw: unknown;
  try {
    raw = await request.json();
  } catch {
    return NextResponse.json({ error: "invalid json body" }, { status: 400 });
  }
  const body = parseFollowupBody(raw);
  if (body === null) {
    return NextResponse.json(
      { error: "owner_user_id (uuid) and due_date (YYYY-MM-DD) required" },
      { status: 400 },
    );
  }
  try {
    const followup = await cpCreateInsightFollowup(tid, engagementId, insightId, body);
    return NextResponse.json({ followup, source: "cp" }, { status: 201 });
  } catch (e) {
    return nextResponseFromStrategistCpFetchError(e);
  }
}

function parseFollowupBody(raw: unknown): FollowupBody | null {
  if (raw === null || typeof raw !== "object") return null;
  const owner = (raw as { owner_user_id?: unknown }).owner_user_id;
  const due = (raw as { due_date?: unknown }).due_date;
  if (typeof owner !== "string" || !UUID_RE.test(owner)) return null;
  if (typeof due !== "string" || !ISO_DATE.test(due)) return null;
  return { owner_user_id: owner, due_date: due };
}
