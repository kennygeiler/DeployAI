import type { Metadata } from "next";
import { z } from "zod";

import { EngagementTimeline } from "@/components/epic9/EngagementTimeline.client";
import { TimelineView } from "@/components/timeline/TimelineView.client";
import { ALLOWED_SOURCE_KINDS } from "@/lib/internal/ledger-cp";
import { cpListMatrixNodes } from "@/lib/internal/matrix-cp";
import { requireCanonicalRead } from "@/lib/internal/strategist-surface";

export const metadata: Metadata = {
  title: "Engagement timeline",
  description: "Append-only ledger of every event in this engagement.",
};

const STAKEHOLDER_PARAM = "timeline.stakeholder";
const SHORT_STAKEHOLDER_PARAM = "stakeholder";
const EVENT_PARAM = "event";
const SOURCE_KIND_PARAM = "source_kind";

const zUuid = z.string().uuid();

function readUuid(value: string | string[] | undefined): string | null {
  if (typeof value !== "string") return null;
  const parsed = zUuid.safeParse(value.trim());
  return parsed.success ? parsed.data : null;
}

function readSourceKinds(value: string | string[] | undefined): string[] {
  if (typeof value !== "string") return [];
  return value
    .split(",")
    .map((s) => s.trim())
    .filter((s) => s.length > 0 && ALLOWED_SOURCE_KINDS.has(s));
}

function truncateUuid(id: string): string {
  return `${id.slice(0, 8)}…`;
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
  const stakeholderId = readUuid(sp[STAKEHOLDER_PARAM]) ?? readUuid(sp[SHORT_STAKEHOLDER_PARAM]);
  const eventId = readUuid(sp[EVENT_PARAM]);
  const initialSourceKinds = readSourceKinds(sp[SOURCE_KIND_PARAM]);

  if (!stakeholderId && !eventId) {
    return <TimelineView engagementId={engagementId} />;
  }

  let nodeTitle: string | null = null;
  if (stakeholderId) {
    const nodes = await cpListMatrixNodes(actor.tenantId!.trim(), engagementId).catch(
      () => [] as Awaited<ReturnType<typeof cpListMatrixNodes>>,
    );
    const node = nodes.find((n) => n.id === stakeholderId) ?? null;
    nodeTitle = node?.title ?? null;
  }

  const affectsFilter = stakeholderId
    ? {
        nodeId: stakeholderId,
        nodeTitle: nodeTitle ?? truncateUuid(stakeholderId),
        clearHref: `/engagements/${encodeURIComponent(engagementId)}/timeline`,
      }
    : null;

  return (
    <div className="space-y-4 p-4" data-testid="timeline-view-stakeholder-scoped">
      <EngagementTimeline
        engagementId={engagementId}
        affectsFilter={affectsFilter}
        eventId={eventId}
        initialSourceKinds={initialSourceKinds}
      />
    </div>
  );
}
