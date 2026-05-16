import type { Metadata } from "next";

import { InMeetingAlertDemo } from "@/components/epic9/InMeetingAlertDemo.client";
import { requireCanonicalRead } from "@/lib/internal/strategist-surface";
import { loadMorningDigestTopItemsResultForActor } from "@/lib/strategist-data/strategist-surface-data";

export const metadata: Metadata = {
  title: "In-meeting alert",
  description:
    "Epic 9.1–9.4 — meeting presence, three-item budget, correction vs dismissal, carryover to Action Queue.",
};

export default async function InMeetingPage() {
  const actor = await requireCanonicalRead();
  const digestLoad = await loadMorningDigestTopItemsResultForActor(actor);
  return <InMeetingAlertDemo initialDigestItems={digestLoad.items} />;
}
