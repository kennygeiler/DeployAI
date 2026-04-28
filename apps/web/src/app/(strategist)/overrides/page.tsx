import type { Metadata } from "next";

import { OverrideHistorySurface } from "@/components/epic10/OverrideHistorySurface.client";
import { requireCanonicalRead } from "@/lib/internal/strategist-surface";

export const metadata: Metadata = {
  title: "Override history",
  description: "Epic 10 — strategist overrides, propagation preview, and history.",
};

export default async function OverrideHistoryPage() {
  await requireCanonicalRead();
  return <OverrideHistorySurface />;
}
