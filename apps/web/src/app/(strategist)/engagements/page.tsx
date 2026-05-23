import type { Metadata } from "next";

import { EngagementPortfolio } from "@/components/epic9/EngagementPortfolio.client";
import { PortfolioInsights } from "@/components/epic9/PortfolioInsights.client";
import { requireCanonicalRead } from "@/lib/internal/strategist-surface";

export const metadata: Metadata = {
  title: "Engagements",
  description: "Phase 3 — the portfolio of customer deployments your team is running.",
};

export default async function EngagementsPage() {
  await requireCanonicalRead();
  return (
    <div className="max-w-5xl space-y-6">
      <PortfolioInsights />
      <EngagementPortfolio />
    </div>
  );
}
