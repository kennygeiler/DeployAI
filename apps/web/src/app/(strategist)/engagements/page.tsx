import type { Metadata } from "next";
import { redirect } from "next/navigation";

import { EngagementPortfolio } from "@/components/epic9/EngagementPortfolio.client";
import { PortfolioInsights } from "@/components/epic9/PortfolioInsights.client";
import { cpListEngagements } from "@/lib/internal/engagements-cp";
import { requireCanonicalRead } from "@/lib/internal/strategist-surface";

export const metadata: Metadata = {
  title: "Engagements",
  description: "Phase 3 — the portfolio of customer deployments your team is running.",
};

export default async function EngagementsPage() {
  const actor = await requireCanonicalRead();
  // Sprint 1 inc 2 — empty tenant bounces into the first-run wizard.
  // Done server-side so a fresh install lands on /onboarding without ever
  // rendering an empty portfolio. The /onboarding page mirrors the inverse
  // redirect once any engagement exists, so the wizard can't be re-opened
  // by URL on a configured tenant.
  const tid = actor.tenantId?.trim();
  if (tid) {
    let isEmpty = false;
    try {
      const engagements = await cpListEngagements(tid);
      isEmpty = engagements.length === 0;
    } catch {
      // CP unreachable — fall through; EngagementPortfolio's client fetch
      // surfaces the same error to the user.
    }
    if (isEmpty) {
      // `redirect()` throws a Next-internal NEXT_REDIRECT signal — keep it
      // outside the try so the catch above doesn't swallow it.
      redirect("/onboarding");
    }
  }
  return (
    <div className="max-w-5xl space-y-6">
      <PortfolioInsights />
      <EngagementPortfolio />
    </div>
  );
}
