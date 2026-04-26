import { NextResponse } from "next/server";

import { getActorFromHeaders } from "@/lib/internal/actor";
import {
  loadStrategistActivityForActor,
  type StrategistActivitySnapshot,
} from "@/lib/internal/load-strategist-activity";

/**
 * BFF: strategist top-rail (ingest activity + control-plane liveness) for client polling
 * and browser consistency with the server layout.
 */
export async function GET() {
  const actor = await getActorFromHeaders();
  if (!actor) {
    return new NextResponse("Unauthorized", { status: 401 });
  }
  const s: StrategistActivitySnapshot = await loadStrategistActivityForActor(actor);
  return NextResponse.json(s, { status: 200 });
}
