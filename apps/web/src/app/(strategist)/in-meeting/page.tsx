import type { Metadata } from "next";

import { InMeetingAlertDemo } from "@/components/epic9/InMeetingAlertDemo.client";
import { requireCanonicalRead } from "@/lib/internal/strategist-surface";

export const metadata: Metadata = {
  title: "In-meeting alert",
  description:
    "MVP Track D — in-meeting alert with digest-aligned mock citations (Epic 9 thin slice).",
};

export default async function InMeetingPage() {
  await requireCanonicalRead();
  return <InMeetingAlertDemo />;
}
