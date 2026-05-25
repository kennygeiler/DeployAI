import type { Metadata } from "next";

import { TimelineView } from "@/components/timeline/TimelineView.client";
import { requireCanonicalRead } from "@/lib/internal/strategist-surface";

export const metadata: Metadata = {
  title: "Engagement timeline",
  description: "Append-only ledger of every event in this engagement.",
};

export default async function EngagementTimelinePage({
  params,
}: {
  params: Promise<{ engagementId: string }>;
}) {
  await requireCanonicalRead();
  const { engagementId } = await params;
  return <TimelineView engagementId={engagementId} />;
}
