import type { Metadata } from "next";

import { ValidationQueueSurface } from "@/components/epic9/ValidationQueueSurface.client";
import { requireCanonicalRead } from "@/lib/internal/strategist-surface";

export const metadata: Metadata = {
  title: "Validation queue",
  description: "Epic 9.6 — User Validation Queue with confirm / modify / reject.",
};

export default async function ValidationQueuePage() {
  await requireCanonicalRead();
  return <ValidationQueueSurface />;
}
