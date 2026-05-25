import type { Metadata } from "next";
import Link from "next/link";

import { EngagementDetail } from "@/components/epic9/EngagementDetail.client";
import { requireCanonicalRead } from "@/lib/internal/strategist-surface";

export const metadata: Metadata = {
  title: "Engagement",
  description: "Phase 4 — one customer deployment: its team, phase, and log.",
};

export default async function EngagementDetailPage({
  params,
}: {
  params: Promise<{ engagementId: string }>;
}) {
  await requireCanonicalRead();
  const { engagementId } = await params;
  return (
    <>
      <div className="flex justify-end p-4">
        <Link
          href={`/engagements/${encodeURIComponent(engagementId)}/timeline`}
          className="text-primary text-sm underline-offset-4 hover:underline"
        >
          View timeline
        </Link>
      </div>
      <EngagementDetail engagementId={engagementId} />
    </>
  );
}
