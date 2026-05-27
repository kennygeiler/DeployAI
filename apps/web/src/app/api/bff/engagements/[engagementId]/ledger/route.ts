import { type NextRequest, NextResponse } from "next/server";

import { decideSync } from "@deployai/authz";

import { getActorFromHeaders } from "@/lib/internal/actor";
import { cpListLedger, type LedgerListOpts } from "@/lib/internal/ledger-cp";
import { nextResponseFromStrategistCpFetchError } from "@/lib/internal/strategist-bff-cp-error";
import { strategistQueueBffCpMisconfiguredResponse } from "@/lib/internal/strategist-queues-route-guard";

type Ctx = { params: Promise<{ engagementId: string }> };

const DEFAULT_LIMIT = 100;
const MAX_LIMIT = 500;

// Mirrors the CP source_kind enum (docs/design/timeline-ledger.md §3.1 + §4.3).
// Validate at the BFF boundary so unknown values 400 here instead of silent-empty
// at CP.
const ALLOWED_SOURCE_KINDS = new Set([
  "email_ingest",
  "meeting_webhook",
  "manual_capture",
  "llm_proposal_created",
  "proposal_accepted",
  "proposal_rejected",
  "matrix_node_created",
  "matrix_node_updated",
  "matrix_node_deleted",
  "matrix_edge_created",
  "matrix_edge_deleted",
  "insight_opened",
  "insight_closed",
  "recommendation_emitted",
  "recommendation_actioned",
  "engagement_phase_change",
  "member_added",
  "member_removed",
  "settings_change",
  "audit_other",
  "user_provisioned",
  "audit_decision",
  "insight_snoozed",
  "followup_task_created",
  // v2 Phase 5 Wave 3I — outbound MCP audit + config-change kinds. Wave 2D
  // emits the call-status kinds from ``mcp_client.py``; Wave 2E/2F emit
  // the config + killswitch + oauth-rotation kinds. The "External (MCP)"
  // timeline chip filters to the call subset; the admin audit panel
  // surfaces the same rows tenant-wide.
  "mcp_outbound_call",
  "mcp_outbound_blocked",
  "mcp_outbound_rate_limited",
  "mcp_outbound_denied",
  "mcp_outbound_killswitch_changed",
  "mcp_config_created",
  "mcp_config_updated",
  "mcp_config_deleted",
  "mcp_oauth_token_rotated",
]);

function parseLimit(raw: string | null): number | { error: NextResponse } {
  if (raw === null) return DEFAULT_LIMIT;
  const parsed = Number(raw);
  if (!Number.isFinite(parsed) || !Number.isInteger(parsed) || parsed < 1 || parsed > MAX_LIMIT) {
    return { error: NextResponse.json({ error: "invalid limit" }, { status: 400 }) };
  }
  return parsed;
}

function parseIso(raw: string | null, field: string): string | null | { error: NextResponse } {
  if (raw === null) return null;
  const d = new Date(raw);
  if (Number.isNaN(d.getTime())) {
    return { error: NextResponse.json({ error: `invalid ${field}` }, { status: 400 }) };
  }
  return raw;
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
  const { engagementId } = await ctx.params;
  const tid = actor.tenantId!.trim();
  const sp = new URL(request.url).searchParams;

  const limit = parseLimit(sp.get("limit"));
  if (typeof limit === "object") return limit.error;
  const from = parseIso(sp.get("from"), "from");
  if (from !== null && typeof from === "object") return from.error;
  const to = parseIso(sp.get("to"), "to");
  if (to !== null && typeof to === "object") return to.error;

  const opts: LedgerListOpts = { limit };
  if (typeof from === "string") opts.from = from;
  if (typeof to === "string") opts.to = to;
  const sourceKindRaw = sp.get("source_kind");
  if (sourceKindRaw) {
    const kinds = sourceKindRaw
      .split(",")
      .map((s) => s.trim())
      .filter((s) => s.length > 0);
    const invalid = kinds.filter((k) => !ALLOWED_SOURCE_KINDS.has(k));
    if (invalid.length > 0) {
      return NextResponse.json(
        { error: `unknown source_kind value(s): ${invalid.join(", ")}` },
        { status: 400 },
      );
    }
    opts.source_kind = kinds;
  }
  const actorId = sp.get("actor_id");
  if (actorId) opts.actor_id = actorId;
  const affectsKind = sp.get("affects_entity_kind");
  if (affectsKind) opts.affects_entity_kind = affectsKind;
  const affectsId = sp.get("affects_entity_id");
  if (affectsId) {
    if (!/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(affectsId)) {
      return NextResponse.json({ error: "invalid affects_entity_id" }, { status: 400 });
    }
    opts.affects_entity_id = affectsId;
  }
  const cursor = sp.get("cursor");
  if (cursor) opts.cursor = cursor;

  try {
    const body = await cpListLedger(tid, engagementId, opts);
    return NextResponse.json({ ...body, source: "cp" }, { status: 200 });
  } catch (e) {
    return nextResponseFromStrategistCpFetchError(e);
  }
}
