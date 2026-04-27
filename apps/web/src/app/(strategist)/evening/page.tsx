import type { Metadata } from "next";

import { EveningSynthesisClient } from "@/components/epic8/EveningSynthesis.client";
import { listSolidificationQueue } from "@/lib/bff/strategist-queues-store";
import { requireCanonicalRead } from "@/lib/internal/strategist-surface";
import {
  eveningSynthesisBannerMessage,
  loadEveningSynthesisResult,
} from "@/lib/strategist-data/strategist-surface-data";

export const metadata: Metadata = {
  title: "Evening synthesis",
  description: "End-of-day synthesis (Epic 8, FR35).",
};

export default async function EveningPage() {
  const actor = await requireCanonicalRead();
  const eveningLoad = await loadEveningSynthesisResult();
  const eveningBanner = eveningSynthesisBannerMessage(eveningLoad);
  const solidificationPending = listSolidificationQueue(actor.tenantId ?? null).length;
  return (
    <EveningSynthesisClient
      initialCandidates={eveningLoad.candidates}
      initialPatterns={eveningLoad.patterns}
      eveningBanner={eveningBanner}
      solidificationPendingCount={solidificationPending}
    />
  );
}
