import { notFound } from "next/navigation";

import { requireCanonicalRead } from "@/lib/internal/strategist-surface";
import { loadStrategistEvidenceItemForActor } from "@/lib/strategist-data/strategist-surface-data";
import { EvidenceNodePageClient } from "./EvidenceNodePage.client";

type PageProps = { params: Promise<{ nodeId: string }> };

export default async function EvidenceNodePage({ params }: PageProps) {
  const { nodeId: raw } = await params;
  const nodeId = decodeURIComponent(raw);
  const actor = await requireCanonicalRead();
  const item = await loadStrategistEvidenceItemForActor(actor, nodeId);
  if (!item) {
    notFound();
  }
  return <EvidenceNodePageClient item={item} />;
}
