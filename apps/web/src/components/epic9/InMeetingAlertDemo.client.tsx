"use client";

import * as React from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Ban, Pencil } from "lucide-react";
import { toast } from "sonner";

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
  const router = useRouter();
  const { agentDegraded } = useStrategistSurface();
  const [expanded, setExpanded] = React.useState(false);
  const [citationReady, setCitationReady] = React.useState(false);
  const panelState = agentDegraded ? "degraded" : item.state;

  React.useEffect(() => {
    let r1 = 0;
    let r2 = 0;
    r1 = requestAnimationFrame(() => {
      r2 = requestAnimationFrame(() => setCitationReady(true));
    });
    return () => {
      cancelAnimationFrame(r1);
      cancelAnimationFrame(r2);
    };
  }, []);

  return (
    <div className="min-w-0 rounded-md border border-border bg-paper-100/80 p-2">
      <p className="text-ink-800 line-clamp-2 text-xs font-medium">{item.label}</p>
      <div className="mt-1.5 min-w-0" data-in-meeting-primary-item={item.id}>
        {citationReady ? (
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
        ) : (
          <div
            className="bg-paper-200/90 h-8 w-full max-w-[10rem] animate-pulse rounded"
            data-fr36-citation-placeholder="true"
            aria-hidden
          />
        )}
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
      <div
        className="mt-3 flex min-h-9 flex-wrap items-center gap-4"
        data-fr37-action-row={item.id}
      >
        <Button
          type="button"
          variant="default"
          size="sm"
          className="bg-evidence-100 text-evidence-900 border-evidence-600/30 hover:bg-evidence-100/90 focus-visible:ring-evidence-700 inline-flex min-h-9 gap-2 border px-3 text-xs font-semibold shadow-none"
          onClick={() => {
            void (async () => {
              await fetch("/api/bff/in-meeting-feedback", {
                method: "POST",
                headers: { "content-type": "application/json" },
                body: JSON.stringify({ itemId: item.id, action: "correct" }),
              });
              onHandled(item.id, "correct");
              router.push(`/overrides?focus=${encodeURIComponent(item.id)}`);
            })();
          }}
        >
          <Pencil className="size-4 shrink-0" aria-hidden />
          Correct
        </Button>
        <Button
          type="button"
          variant="ghost"
          size="sm"
          className="text-ink-700 inline-flex min-h-9 gap-2 px-2"
          onClick={() => {
            void fetch("/api/bff/in-meeting-feedback", {
              method: "POST",
              headers: { "content-type": "application/json" },
              body: JSON.stringify({ itemId: item.id, action: "dismiss" }),
            });
            onHandled(item.id, "dismiss");
          }}
        >
          <Ban className="size-4 shrink-0" aria-hidden />
          Dismiss
        </Button>
      </div>
    </div>
  );
}

/**
 * Epic 9 Stories 9.1–9.4 — meeting presence from activity poll + URL demo flags, three-item budget,
 * correction vs dismissal (FR37), carryover to Action Queue when meeting ends (FR38).
 */
export function InMeetingAlertDemo() {
  const router = useRouter();
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
    void (async () => {
      const res = await fetch("/api/bff/in-meeting-carryover", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ unattendedIds: unattended }),
      });
      if (!res.ok) {
        return;
      }
      const j = (await res.json()) as { inserted?: number };
      const n = typeof j.inserted === "number" ? j.inserted : 0;
      if (n > 0) {
        toast.success(`Carried over ${n} item(s) to the Action Queue`, {
          description: "Triage in Evening synthesis or the Action queue.",
          action: {
            label: "Evening synthesis",
            onClick: () => router.push("/evening"),
          },
        });
      }
    })();
  }, [surface.inMeeting, primary, handled, router]);

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
          ). Detection:{" "}
          <code className="text-ink-800 bg-paper-200 rounded px-1 py-0.5 font-mono text-xs">
            {surface.meetingDetectionSource ?? "—"}
          </code>
          . For local demos without CP stubs, append{" "}
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
          epic91MeetingAlertMarker="active"
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
