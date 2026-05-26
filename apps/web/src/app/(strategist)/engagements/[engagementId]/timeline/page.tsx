import type { Metadata } from "next";

import { EngagementTimeline } from "@/components/epic9/EngagementTimeline.client";
import { TimelineView } from "@/components/timeline/TimelineView.client";
import { cpListMatrixNodes } from "@/lib/internal/matrix-cp";
import { requireCanonicalRead } from "@/lib/internal/strategist-surface";

export const metadata: Metadata = {
  title: "Engagement timeline",
  description: "Append-only ledger of every event in this engagement.",
};

const STAKEHOLDER_PARAM = "timeline.stakeholder";

function readStakeholderParam(value: string | string[] | undefined): string | null {
  if (typeof value !== "string") return null;
  const trimmed = value.trim();
  return trimmed.length === 0 ? null : trimmed;
}

function stakeholderEmail(attributes: Record<string, unknown>): string | null {
  const e = attributes["email"];
  return typeof e === "string" && e.length > 0 ? e : null;
}

export default async function EngagementTimelinePage({
  params,
  searchParams,
}: {
  params: Promise<{ engagementId: string }>;
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const actor = await requireCanonicalRead();
  const { engagementId } = await params;
  const sp = await searchParams;
  const stakeholderId = readStakeholderParam(sp[STAKEHOLDER_PARAM]);

  if (!stakeholderId) {
    return <TimelineView engagementId={engagementId} />;
  }

  const nodes = await cpListMatrixNodes(actor.tenantId!.trim(), engagementId).catch(
    () => [] as Awaited<ReturnType<typeof cpListMatrixNodes>>,
  );
  const node = nodes.find((n) => n.id === stakeholderId) ?? null;
  const filter =
    node && node.node_type === "stakeholder"
      ? {
          id: node.id,
          title: node.title,
          email: stakeholderEmail(node.attributes),
          evidenceEventIds: node.evidence_event_ids,
          clearHref: `/engagements/${encodeURIComponent(engagementId)}/timeline`,
        }
      : null;

  if (!filter) {
    return <TimelineView engagementId={engagementId} />;
  }

  return (
    <div className="space-y-4 p-4" data-testid="timeline-view-stakeholder-scoped">
      <EngagementTimeline engagementId={engagementId} stakeholderFilter={filter} />
    </div>
  );
}
