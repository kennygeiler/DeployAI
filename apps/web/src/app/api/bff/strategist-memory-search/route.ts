import { type NextRequest, NextResponse } from "next/server";

import { searchMemoryMock } from "@/lib/bff/memory-search-mock";
import { getStrategistLocalDateForServer } from "@/lib/internal/strategist-local-date";
import { getActorFromHeaders } from "@/lib/internal/actor";
import { decideSync } from "@deployai/authz";
import {
  loadMorningDigestTopItemsResultForActor,
  loadPhaseTrackingRowsResultForActor,
} from "@/lib/strategist-data/strategist-surface-data";

/**
 * GET /api/bff/strategist-memory-search?q=...
 *
 * When `DEPLOYAI_CANONICAL_MEMORY_SEARCH_URL` is set, proxies that endpoint (appends `q` as
 * `query` param). Otherwise scans digest + phase-tracking rows returned for the signed-in actor
 * (no static fixtures).
 */
export async function GET(request: NextRequest) {
  const actor = await getActorFromHeaders();
  if (!actor) {
    return new NextResponse("Unauthorized", { status: 401 });
  }
  const d = decideSync(actor, "canonical:read", { kind: "canonical_memory" });
  if (!d.allow) {
    return new NextResponse("Forbidden", { status: 403 });
  }
  const q = request.nextUrl.searchParams.get("q")?.trim() ?? "";
  const remote = process.env.DEPLOYAI_CANONICAL_MEMORY_SEARCH_URL?.trim();
  if (remote) {
    try {
      const u = new URL(remote);
      u.searchParams.set("q", q);
      const r = await fetch(u, { method: "GET", cache: "no-store" });
      const text = await r.text();
      return new NextResponse(text, {
        status: r.status,
        headers: { "content-type": r.headers.get("content-type") ?? "application/json" },
      });
    } catch (e) {
      const m = e instanceof Error ? e.message : "upstream error";
      return NextResponse.json({ error: m, source: "proxy" }, { status: 502 });
    }
  }
  const today = getStrategistLocalDateForServer();
  const digestResult = await loadMorningDigestTopItemsResultForActor(actor);
  const phaseResult = await loadPhaseTrackingRowsResultForActor(actor, today);
  const hits = searchMemoryMock(q, digestResult.items, phaseResult.items);
  const dataTrusted = digestResult.dataTrusted && phaseResult.dataTrusted;
  return NextResponse.json(
    { source: "in_process", dataTrusted, hits, query: q },
    { status: 200 },
  );
}
