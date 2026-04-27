import type { Metadata } from "next";

import { MorningDigestClient } from "@/components/epic8/MorningDigest.client";
import { requireCanonicalRead } from "@/lib/internal/strategist-surface";
import {
  loadMorningDigestTopItemsResult,
  morningDigestBannerMessage,
} from "@/lib/strategist-data/strategist-surface-data";

export const metadata: Metadata = {
  title: "Morning digest",
  description: "Oracle morning digest (Epic 8, FR34).",
};

export default async function DigestPage() {
  await requireCanonicalRead();
  const digestLoad = await loadMorningDigestTopItemsResult();
  const digestBanner = morningDigestBannerMessage(digestLoad);
  return <MorningDigestClient topItems={digestLoad.items} digestBanner={digestBanner} />;
}
