import type { Metadata } from "next";

import { PhaseTrackingClient } from "@/components/epic8/PhaseTracking.client";
import { getStrategistLocalDateForServer } from "@/lib/internal/strategist-local-date";
import { requireCanonicalRead } from "@/lib/internal/strategist-surface";
import {
  loadPhaseTrackingRowsResult,
  phaseTrackingBannerMessage,
} from "@/lib/strategist-data/strategist-surface-data";

export const metadata: Metadata = {
  title: "Phase & task tracking",
  description: "Phase and Action Queue tracking (Epic 8, FR39).",
};

export default async function PhaseTrackingPage() {
  await requireCanonicalRead();
  const today = getStrategistLocalDateForServer();
  const phaseLoad = await loadPhaseTrackingRowsResult(today);
  const phaseTrackingBanner = phaseTrackingBannerMessage(phaseLoad);
  return (
    <PhaseTrackingClient
      initialPhaseTrackingRows={phaseLoad.items}
      phaseTrackingBanner={phaseTrackingBanner}
    />
  );
}
