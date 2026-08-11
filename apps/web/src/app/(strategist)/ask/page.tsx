import type { Metadata } from "next";

import { AskKennyGlobal } from "@/components/ask/AskKennyGlobal.client";
import { requireCanonicalRead } from "@/lib/internal/strategist-surface";

export const metadata: Metadata = {
  title: "Ask Kenny",
  description: "Ask Agent Kenny about any engagement — answers grounded in the ledger.",
};

export default async function AskPage() {
  await requireCanonicalRead();
  return <AskKennyGlobal />;
}
