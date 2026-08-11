import { type NextRequest, NextResponse } from "next/server";
import { z } from "zod";

import { decideSync } from "@deployai/authz";

import { isStoredReviewItemKind } from "@/lib/bff/review-types";
import { getActorFromHeaders } from "@/lib/internal/actor";
import { cpListReviewItems } from "@/lib/internal/review-inbox-cp";
import { nextResponseFromStrategistCpFetchError } from "@/lib/internal/strategist-bff-cp-error";
import { strategistQueueBffCpMisconfiguredResponse } from "@/lib/internal/strategist-queues-route-guard";

/**
 * Pilot-refresh E1 — list review items for the unified Review Inbox.
 * Filters: `kind` (stored kinds only — extraction proposals come from the
 * engagement detail aggregate), `status`, `engagementId`.
 */

const ItemSchema = z.object({
  id: z.string(),
  tenant_id: z.string(),
  engagement_id: z.string().nullable(),
  kind: z.string(),
  status: z.string(),
  payload: z.record(z.string(), z.unknown()),
  created_by: z.string().nullable(),
  resolved_by: z.string().nullable(),
  resolution_note: z.string().nullable(),
  created_at: z.string(),
  resolved_at: z.string().nullable(),
});

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const STATUSES = ["open", "resolved", "dismissed"] as const;

export async function GET(request: NextRequest) {
  const actor = await getActorFromHeaders();
  if (!actor) {
    return new NextResponse("Unauthorized", { status: 401 });
  }
  const d = decideSync(actor, "canonical:read", {
    kind: "canonical_memory",
    tenantId: actor.tenantId,
  });
  if (!d.allow) {
    return new NextResponse("Forbidden", { status: 403 });
  }
  const cpMisconfigured = strategistQueueBffCpMisconfiguredResponse(actor.tenantId);
  if (cpMisconfigured) {
    return cpMisconfigured;
  }
  const tid = actor.tenantId!.trim();

  const sp = request.nextUrl.searchParams;
  const kind = sp.get("kind");
  if (kind !== null && !isStoredReviewItemKind(kind)) {
    return NextResponse.json({ error: "invalid kind" }, { status: 400 });
  }
  const status = sp.get("status");
  if (status !== null && !(STATUSES as readonly string[]).includes(status)) {
    return NextResponse.json({ error: "invalid status" }, { status: 400 });
  }
  const engagementId = sp.get("engagementId");
  if (engagementId !== null && !UUID_RE.test(engagementId)) {
    return NextResponse.json({ error: "invalid engagementId" }, { status: 400 });
  }

  try {
    const items = await cpListReviewItems(tid, { kind, status, engagementId });
    const validated = z.array(ItemSchema).parse(items);
    return NextResponse.json({ items: validated, source: "cp" }, { status: 200 });
  } catch (e) {
    return nextResponseFromStrategistCpFetchError(e);
  }
}
