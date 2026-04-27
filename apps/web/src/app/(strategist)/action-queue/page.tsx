import type { Metadata } from "next";

import { ActionQueueTable } from "@/components/epic9/ActionQueueTable.client";
import { requireCanonicalRead } from "@/lib/internal/strategist-surface";

export const metadata: Metadata = {
  title: "Action queue",
  description: "Epic 9.5 — claim, in-progress, and resolve strategist action items.",
};

export default async function ActionQueuePage() {
  await requireCanonicalRead();
  return <ActionQueueTable />;
}
