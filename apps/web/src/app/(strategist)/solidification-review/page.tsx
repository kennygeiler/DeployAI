import type { Metadata } from "next";

import { SolidificationQueueSurface } from "@/components/epic9/SolidificationQueueSurface.client";
import { requireCanonicalRead } from "@/lib/internal/strategist-surface";

export const metadata: Metadata = {
  title: "Solidification review",
  description: "Epic 9.7 — Class B solidification review queue.",
};

export default async function SolidificationReviewPage() {
  await requireCanonicalRead();
  return <SolidificationQueueSurface />;
}
