import type { Metadata } from "next";

import { InMeetingAlertDemo } from "@/components/epic9/InMeetingAlertDemo.client";
import { requireCanonicalRead } from "@/lib/internal/strategist-surface";

export const metadata: Metadata = {
  title: "In-meeting alert",
  description:
    "Epic 9.1–9.4 — meeting presence, three-item budget, correction vs dismissal, carryover to Action Queue.",
};

export default async function InMeetingPage() {
  await requireCanonicalRead();
  return <InMeetingAlertDemo />;
}
