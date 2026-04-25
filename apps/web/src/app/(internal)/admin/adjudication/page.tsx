import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { decideSync } from "@deployai/authz";

import { getActorFromHeaders } from "@/lib/internal/actor";

export const metadata: Metadata = {
  title: "Admin — Adjudication queue",
  description: "Human review of replay-parity and citation disagreements (Epic 4, Story 4-7).",
};

export default async function AdminAdjudicationPage() {
  const actor = await getActorFromHeaders();
  if (!actor) {
    notFound();
  }
  const d = decideSync(actor, "eval:view_adjudication", { kind: "global" });
  if (!d.allow) {
    notFound();
  }

  return (
    <main
      id="main"
      tabIndex={-1}
      className="mx-auto flex max-w-5xl flex-col gap-6 p-8 outline-none"
    >
      <div>
        <h1 className="text-display font-semibold tracking-tight text-ink-950">Adjudication</h1>
        <p className="text-body text-ink-600 max-w-2xl">
          Queue for human decisions when rule-based and LLM-judge evaluators disagree. Data plane wiring
          (list disputes, record outcomes) follows in a later story; this page is the authenticated
          surface shell.
        </p>
      </div>
      <div className="border border-dashed border-ink-200 rounded-lg p-6 text-body text-ink-500">
        No pending items (placeholder).
      </div>
    </main>
  );
}
