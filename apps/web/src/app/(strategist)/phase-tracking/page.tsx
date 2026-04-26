import type { Metadata } from "next";

import { PhaseTrackingClient } from "@/components/epic8/PhaseTracking.client";
import { requireCanonicalRead } from "@/lib/internal/strategist-surface";

export const metadata: Metadata = {
  title: "Phase & task tracking",
  description: "Phase and Action Queue tracking (Epic 8, FR39).",
};

export default async function PhaseTrackingPage() {
  await requireCanonicalRead();
  return <PhaseTrackingClient />;
}
