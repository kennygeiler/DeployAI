import { type NextRequest, NextResponse } from "next/server";

import { decideSync } from "@deployai/authz";

import {
  normalizeMatrixInsight,
  normalizeTemporalInsight,
  type UnifiedInsight,
} from "@/lib/bff/insight-types";
import { getActorFromHeaders } from "@/lib/internal/actor";
import { cpListMatrixInsights, cpListTemporalInsights } from "@/lib/internal/insights-cp";
import { nextResponseFromStrategistCpFetchError } from "@/lib/internal/strategist-bff-cp-error";
import { strategistQueueBffCpMisconfiguredResponse } from "@/lib/internal/strategist-queues-route-guard";

type Ctx = { params: Promise<{ engagementId: string }> };

/**
 * Pilot-refresh F2 — unified insights read path. Returns BOTH insight
 * models for the engagement as one normalized list (`UnifiedInsight`):
 * Oracle `matrix_insights` rows (`model: "matrix"`, dismiss/resolve) and
 * analyzer `temporal_insights` rows (`model: "temporal"`,
 * snooze/follow-up/dismiss/resolve). `open` rows by default; pass
 * `?status=dismissed` or `?status=resolved` for history.
 */
export async function GET(request: NextRequest, ctx: Ctx) {
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
  const { engagementId } = await ctx.params;
  const tid = actor.tenantId!.trim();
  const statusParam = request.nextUrl.searchParams.get("status");
  const allowed = ["open", "dismissed", "resolved"] as const;
  const status: (typeof allowed)[number] | null =
    statusParam && (allowed as readonly string[]).includes(statusParam)
      ? (statusParam as (typeof allowed)[number])
      : statusParam === null
        ? "open"
        : null;
  if (status === null) {
    return NextResponse.json({ error: "invalid status" }, { status: 400 });
  }
  try {
    const [matrix, temporal] = await Promise.all([
      cpListMatrixInsights(tid, engagementId, status),
      cpListTemporalInsights(tid, engagementId, status),
    ]);
    const insights: UnifiedInsight[] = [
      ...matrix.map(normalizeMatrixInsight),
      ...temporal.map(normalizeTemporalInsight),
    ];
    return NextResponse.json({ insights, source: "cp" }, { status: 200 });
  } catch (e) {
    return nextResponseFromStrategistCpFetchError(e);
  }
}
