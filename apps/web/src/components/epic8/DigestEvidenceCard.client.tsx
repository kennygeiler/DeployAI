"use client";

import * as React from "react";
import Link from "next/link";
import { ChevronRight } from "lucide-react";

import { CitationChip, EvidencePanel } from "@deployai/shared-ui";
import type { DigestTopItem } from "@/lib/epic8/mock-digest";
import { useStrategistSurface } from "@/lib/epic8/strategist-surface-context";

export type DigestEvidenceCardProps = {
  item: DigestTopItem;
  headingLevel?: "h2" | "h3";
  /** When on dedicated `/evidence/:id` page, start with panel open (Story 8.4). */
  defaultExpanded?: boolean;
};

/** CitationChip + inline EvidencePanel; “navigate to source” deep-link (Story 8.4). */
export function DigestEvidenceCard({
  item,
  headingLevel = "h2",
  defaultExpanded = false,
}: DigestEvidenceCardProps) {
  const { agentDegraded } = useStrategistSurface();
  const [expanded, setExpanded] = React.useState(defaultExpanded);
  const H = headingLevel;
  const titleId = `digest-title-${item.id}`;
  const panelState = agentDegraded ? "degraded" : item.state;

  return (
    <section
      className="bg-card border-border flex min-h-0 min-w-0 flex-col gap-3 rounded-lg border p-4 shadow-sm"
      aria-labelledby={titleId}
    >
      <div className="min-w-0">
        <H id={titleId} className="text-foreground text-base font-semibold tracking-tight">
          {item.label}
        </H>
        <div className="mt-2 flex min-w-0 flex-wrap items-center gap-2">
          <CitationChip
            id={`citation-${item.id}`}
            label={item.preview.citationId.slice(0, 8)}
            expanded={expanded}
            onToggleExpand={() => {
              setExpanded((e) => !e);
            }}
            variant="inline"
            preview={item.preview}
            onViewEvidence={() => {
              setExpanded(true);
            }}
            onOverride={() => {}}
            onCopyLink={() => {}}
            onCiteInOverride={() => {}}
          />
        </div>
      </div>
      {expanded ? (
        <EvidencePanel
          id={`evidence-${item.id}`}
          visible={expanded}
          retrievalPhase={item.retrievalPhase}
          metadata={item.metadata}
          state={panelState}
          bodyText={item.bodyText}
          evidenceSpan={item.evidenceSpan}
          variant="compact"
          footer={
            <Link
              href={`/evidence/${encodeURIComponent(item.id)}`}
              className="text-evidence-700 focus-visible:ring-ring inline-flex items-center gap-1 text-sm font-medium underline-offset-2 hover:underline focus-visible:rounded focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-offset-2"
            >
              Navigate to source
              <ChevronRight className="size-3.5 shrink-0" aria-hidden />
            </Link>
          }
        />
      ) : null}
    </section>
  );
}
