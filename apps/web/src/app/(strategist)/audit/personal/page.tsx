import type { Metadata } from "next";

import { PersonalAuditSurface } from "@/components/epic10/PersonalAuditSurface.client";
import { requireCanonicalRead } from "@/lib/internal/strategist-surface";

export const metadata: Metadata = {
  title: "Personal audit",
  description: "Epic 10.7 — your strategist actions (scoped, not admin audit).",
};

export default async function PersonalAuditPage() {
  await requireCanonicalRead();
  return <PersonalAuditSurface />;
}
