import type { Metadata } from "next";

import { MorningDigestClient } from "@/components/epic8/MorningDigest.client";
import { requireCanonicalRead } from "@/lib/internal/strategist-surface";

export const metadata: Metadata = {
  title: "Morning digest",
  description: "Oracle morning digest (Epic 8, FR34).",
};

export default async function DigestPage() {
  await requireCanonicalRead();
  return <MorningDigestClient />;
}
