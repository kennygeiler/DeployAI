"use client";

import * as React from "react";
import Link from "next/link";

import { CitationChip, EvidencePanel, InMeetingAlertCard } from "@deployai/shared-ui";

import { Button } from "@/components/ui/button";
import { useStrategistSurface } from "@/lib/epic8/strategist-surface-context";
import { MORNING_DIGEST_TOP, type DigestTopItem } from "@/lib/epic8/mock-digest";
import { splitPrimaryAndRankedOut } from "@/lib/epic9/three-item-budget";

const DEMO_TENANT = "00000000-0000-4000-8000-000000000001";
const STRATEGIST_USER_ID = "local-strategist";

function AlertDigestChip({
  item,
  onHandled,
}: {
  item: DigestTopItem;
  onHandled: (id: string, kind: "dismiss" | "correct") => void;
}) {
  const { agentDegraded } = useStrategistSurface();
  const [expanded, setExpanded] = React.useState(false);
  const panelState = agentDegraded ? "degraded" : item.state;
  return (
    <div className="min-w-0 rounded-md border border-border bg-paper-100/80 p-2">
      <p className="text-ink-800 line-clamp-2 text-xs font-medium">{item.label}</p>
      <div className="mt-1.5 min-w-0" data-in-meeting-primary-item={item.id}>
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
      <div className="mt-3 flex flex-wrap items-center gap-4">
        <Link
          href={`/overrides?focus=${encodeURIComponent(item.id)}`}
          className="text-evidence-800 bg-evidence-100 focus-visible:ring-ring inline-flex min-h-9 items-center rounded-md border border-evidence-600/25 px-3 text-xs font-semibold hover:bg-evidence-100/80 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-offset-2"
          onClick={() => {
            onHandled(item.id, "correct");
          }}
        >
          Correct
        </Link>
        <Button
          type="button"
          variant="ghost"
          size="sm"
          className="text-ink-700"
          onClick={() => {
            void fetch("/api/bff/in-meeting-feedback", {
              method: "POST",
              headers: { "content-type": "application/json" },
              body: JSON.stringify({ itemId: item.id, action: "dismiss" }),
            });
            onHandled(item.id, "dismiss");
          }}
        >
          Dismiss
        </Button>
      </div>
    </div>
  );
}

/**
 * Epic 9 Stories 9.1–9.4 — meeting presence from activity poll + URL demo flags, three-item budget,
 * correction vs dismissal, carryover to Action Queue when meeting ends.
 */
export function InMeetingAlertDemo() {
  const surface = useStrategistSurface();
  const { primary, rankedOut } = React.useMemo(
    () => splitPrimaryAndRankedOut(MORNING_DIGEST_TOP, 3),
    [],
  );
  const [handled, setHandled] = React.useState<Set<string>>(() => new Set());
  const prevMeeting = React.useRef(surface.inMeeting);

  React.useEffect(() => {
    const was = prevMeeting.current;
    prevMeeting.current = surface.inMeeting;
    if (!was || surface.inMeeting) {
      return;
    }
    const unattended = primary.map((p) => p.id).filter((id) => !handled.has(id));
    if (unattended.length === 0) {
      return;
    }
    void fetch("/api/bff/in-meeting-carryover", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ unattendedIds: unattended }),
    });
  }, [surface.inMeeting, primary, handled]);

  const meetingActive = surface.inMeeting;
  const title =
    surface.meetingTitle ?? "Mock: program stand-up (citations = digest-aligned fixtures)";
  const freshness =
    surface.oracleInMeetingAlertAt != null
      ? `Oracle alert @ ${surface.oracleInMeetingAlertAt}`
      : "synced 6s ago (mock trigger)";

  const rankedOutNodes = rankedOut.map((item) => (
    <p key={item.id} className="text-ink-700 text-xs">
      {item.label}
    </p>
  ));

  return (
    <div className="px-4 py-6 md:px-6">
      <div
        className="border-border bg-paper-50 mb-6 max-w-2xl space-y-2 rounded-lg border p-4 text-sm"
        data-mvp-in-meeting-demo
        data-meeting-active={meetingActive ? "true" : "false"}
      >
        <h1 className="text-ink-900 text-lg font-semibold tracking-tight">In-meeting alert</h1>
        <p className="text-ink-700">
          <strong className="font-medium">Epic 9.1–9.4:</strong> meeting presence comes from{" "}
          <code className="text-ink-800 bg-paper-200 rounded px-1 py-0.5 font-mono text-xs">
            GET /api/internal/strategist-activity
          </code>{" "}
          (control plane{" "}
          <code className="text-ink-800 bg-paper-200 rounded px-1 py-0.5 font-mono text-xs">
            /internal/v1/strategist/meeting-presence
          </code>
          ). For local demos without CP stubs, append{" "}
          <code className="text-ink-800 bg-paper-200 rounded px-1 py-0.5 font-mono text-xs">
            ?inMeeting=1
          </code>{" "}
          to the URL. Set{" "}
          <code className="text-ink-800 bg-paper-200 rounded px-1 py-0.5 font-mono text-xs">
            DEPLOYAI_STUB_IN_MEETING_TENANT_IDS
          </code>{" "}
          on the control plane to mark your tenant “in meeting”.
        </p>
      </div>
      {meetingActive ? (
        <InMeetingAlertCard
          tenantId={DEMO_TENANT}
          userId={STRATEGIST_USER_ID}
          meetingTitle={title}
          phaseLabel="P3 — Ecosystem map"
          freshnessLabel={freshness}
          state="active"
          showResetPosition
          rankedOut={rankedOut.length > 0 ? rankedOutNodes : undefined}
        >
          {primary.map((item) => (
            <AlertDigestChip
              key={item.id}
              item={item}
              onHandled={(id) => {
                setHandled((prev) => new Set(prev).add(id));
              }}
            />
          ))}
        </InMeetingAlertCard>
      ) : (
        <p className="text-body text-ink-600 max-w-xl">
          No active meeting signal for this tenant. Use a URL demo flag or control-plane stub env to
          surface the floating card.
        </p>
      )}
    </div>
  );
}
