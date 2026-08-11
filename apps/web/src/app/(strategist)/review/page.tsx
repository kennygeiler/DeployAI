import type { Metadata } from "next";

import { ReviewInbox } from "@/components/review/ReviewInbox.client";
import { requireCanonicalRead } from "@/lib/internal/strategist-surface";

export const metadata: Metadata = {
  title: "Review inbox",
  description:
    "Pilot-refresh E1 — the unified human-in-the-loop queue: extraction proposals, agent escalations, citation disputes, and commitment confirmations.",
};

export default async function ReviewPage() {
  await requireCanonicalRead();
  return (
    <div className="max-w-5xl space-y-6">
      <ReviewInbox />
    </div>
  );
}
