import type { Metadata } from "next";

import { MorningDigestClient } from "@/components/epic8/MorningDigest.client";
import { requireCanonicalRead } from "@/lib/internal/strategist-surface";
import {
  loadMorningDigestTopItemsResultForActor,
  morningDigestBannerMessage,
} from "@/lib/strategist-data/strategist-surface-data";

export const metadata: Metadata = {
  title: "Morning digest",
  description:
    "Ranked deployment signals for the morning review (Epic 8, FR34). Feed provenance depends on environment—this page does not imply a live model retrieval run.",
};

export default async function DigestPage() {
  const actor = await requireCanonicalRead();
  const digestLoad = await loadMorningDigestTopItemsResultForActor(actor);
  const digestBanner = morningDigestBannerMessage(digestLoad);
  return <MorningDigestClient topItems={digestLoad.items} digestBanner={digestBanner} />;
}
