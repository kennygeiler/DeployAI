import type { Metadata } from "next";

import { EveningSynthesisClient } from "@/components/epic8/EveningSynthesis.client";
import { requireCanonicalRead } from "@/lib/internal/strategist-surface";

export const metadata: Metadata = {
  title: "Evening synthesis",
  description: "End-of-day synthesis (Epic 8, FR35).",
};

export default async function EveningPage() {
  await requireCanonicalRead();
  return <EveningSynthesisClient />;
}
