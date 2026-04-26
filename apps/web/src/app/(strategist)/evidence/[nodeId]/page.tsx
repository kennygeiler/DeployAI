import { notFound } from "next/navigation";

import { getStrategistEvidenceByNodeId } from "@/lib/epic8/mock-digest";
import { EvidenceNodePageClient } from "./EvidenceNodePage.client";

type PageProps = { params: Promise<{ nodeId: string }> };

export default async function EvidenceNodePage({ params }: PageProps) {
  const { nodeId: raw } = await params;
  const nodeId = decodeURIComponent(raw);
  const item = getStrategistEvidenceByNodeId(nodeId);
  if (!item) {
    notFound();
  }
  return <EvidenceNodePageClient item={item} />;
}
