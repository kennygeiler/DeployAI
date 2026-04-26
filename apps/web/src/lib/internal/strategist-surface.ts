import { notFound } from "next/navigation";

import { decideSync, type AuthActor } from "@deployai/authz";

import { getActorFromHeaders } from "./actor";

/** Epic 8 strategist surfaces: Oracle digest, phase tracking, evening synthesis. */
export async function requireCanonicalRead(): Promise<AuthActor> {
  const actor = await getActorFromHeaders();
  if (!actor) {
    notFound();
  }
  const d = decideSync(actor, "canonical:read", { kind: "canonical_memory" });
  if (!d.allow) {
    notFound();
  }
  return actor;
}
