"use client";

import * as React from "react";
import Link from "next/link";

import { CitationChip, EvidencePanel, InMeetingAlertCard } from "@deployai/shared-ui";

import { useStrategistSurface } from "@/lib/epic8/strategist-surface-context";
import { MORNING_DIGEST_TOP, type DigestTopItem } from "@/lib/epic8/mock-digest";

const DEMO_TENANT = "00000000-0000-4000-8000-000000000001";

function AlertDigestChip({ item }: { item: DigestTopItem }) {
  const { agentDegraded } = useStrategistSurface();
  const [expanded, setExpanded] = React.useState(false);
  const panelState = agentDegraded ? "degraded" : item.state;
  return (
    <div className="min-w-0">
      <p className="text-ink-800 line-clamp-2 text-xs font-medium">{item.label}</p>
      <div className="mt-1.5 min-w-0">
        <CitationChip
          id={`citation-in-meeting-${item.id}`}
          label={item.preview.citationId.slice(0, 8)}
          expanded={expanded}
          onToggleExpand={() => {
            setExpanded((e) => !e);
          }}
          variant="compact"
          preview={item.preview}
          onViewEvidence={() => {
            setExpanded(true);
          }}
          onOverride={() => {}}
          onCopyLink={() => {}}
          onCiteInOverride={() => {}}
        />
      </div>
      {expanded ? (
        <EvidencePanel
          id={`evidence-in-meeting-${item.id}`}
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
            </Link>
          }
        />
      ) : null}
    </div>
  );
}

/**
 * MVP Track D — in-meeting alert with mock “meeting” context; citation payloads match
 * {@link MORNING_DIGEST_TOP} so evidence links match the morning digest (mvp-operating-plan §4).
 */
export function InMeetingAlertDemo() {
  const items = MORNING_DIGEST_TOP.slice(0, 3);
  return (
    <div className="px-4 py-6 md:px-6">
      <div
        className="border-border bg-paper-50 mb-6 max-w-2xl space-y-2 rounded-lg border p-4 text-sm"
        data-mvp-in-meeting-demo
      >
        <h1 className="text-ink-900 text-lg font-semibold tracking-tight">In-meeting alert</h1>
        <p className="text-ink-700">
          <strong className="font-medium">MVP (mock):</strong> this page simulates a meeting without
          calendar integration. The floating card is{" "}
          <code className="text-ink-800 bg-paper-200 rounded px-1 py-0.5 font-mono text-xs">
            InMeetingAlertCard
          </code>{" "}
          with the same top citations as the{" "}
          <Link
            href="/digest"
            className="text-evidence-800 focus-visible:ring-ring font-medium underline-offset-2 hover:underline focus-visible:rounded focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-offset-2"
          >
            morning digest
          </Link>{" "}
          — “Navigate to source” resolves to the same{" "}
          <code className="text-ink-800 bg-paper-200 rounded px-1 py-0.5 font-mono text-xs">
            /evidence/:nodeId
          </code>{" "}
          nodes.
        </p>
      </div>
      <InMeetingAlertCard
        tenantId={DEMO_TENANT}
        meetingTitle="Mock: program stand-up (citations = digest top 3)"
        phaseLabel="P3 — Ecosystem map"
        freshnessLabel="synced 6s ago (mock trigger)"
        state="active"
        positionStorageKey="tenant:mvp:track-d:in-meeting-demo"
      >
        {items.map((item) => (
          <AlertDigestChip key={item.id} item={item} />
        ))}
      </InMeetingAlertCard>
    </div>
  );
}
