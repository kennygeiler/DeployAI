import type { Metadata } from "next";

import { EngagementBrief } from "@/components/engagements/brief/EngagementBrief.client";
import { requireCanonicalRead } from "@/lib/internal/strategist-surface";

export const metadata: Metadata = {
  title: "Engagement",
  description:
    "The Brief — one customer deployment: what changed, what needs you, and the deal narrative.",
};

export default async function EngagementDetailPage({
  params,
}: {
  params: Promise<{ engagementId: string }>;
}) {
  await requireCanonicalRead();
  const { engagementId } = await params;
  return <EngagementBrief engagementId={engagementId} />;
}
