import { NextResponse } from "next/server";

import { decideSync } from "@deployai/authz";

import { getActorFromHeaders } from "@/lib/internal/actor";
import { cpListEvalRuns, EVAL_RUNS_LIMIT_MAX } from "@/lib/internal/eval-runs-cp";
import { nextResponseFromStrategistCpFetchError } from "@/lib/internal/strategist-bff-cp-error";
import { strategistQueueBffCpMisconfiguredResponse } from "@/lib/internal/strategist-queues-route-guard";

/**
 * Wave 4 (G8) — admin BFF for the eval-run history list.
 *
 * Proxies ``GET /internal/v1/admin/eval-runs`` for the Agent Kenny admin
 * dashboard's "Eval history" section. Same guard chain as the dashboard's
 * own BFF proxy (agent_kenny_dashboard): actor → ``internal:proxy`` authz
 * → CP env check → forward. Eval runs are platform-level ops data (no
 * tenant scope on the CP side); the authz gate keeps the surface limited
 * to the same roles that can see the rest of the dashboard.
 */
export async function GET(req: Request) {
  const actor = await getActorFromHeaders();
  if (!actor) {
    return new NextResponse("Unauthorized", { status: 401 });
  }
  const d = decideSync(actor, "internal:proxy", {
    kind: "canonical_memory",
    tenantId: actor.tenantId,
  });
  if (!d.allow) {
    return new NextResponse("Forbidden", { status: 403 });
  }
  const cpMisconfigured = strategistQueueBffCpMisconfiguredResponse(actor.tenantId);
  if (cpMisconfigured) return cpMisconfigured;

  const url = new URL(req.url);
  const limitRaw = url.searchParams.get("limit");
  let limit: number | undefined;
  if (limitRaw !== null) {
    const n = Number.parseInt(limitRaw, 10);
    if (!Number.isFinite(n) || n < 1 || n > EVAL_RUNS_LIMIT_MAX) {
      return new NextResponse(`Bad Request: limit must be 1..${EVAL_RUNS_LIMIT_MAX}`, {
        status: 400,
      });
    }
    limit = n;
  }

  try {
    const runs = await cpListEvalRuns({ limit });
    return NextResponse.json({ runs }, { status: 200 });
  } catch (e) {
    return nextResponseFromStrategistCpFetchError(e);
  }
}
