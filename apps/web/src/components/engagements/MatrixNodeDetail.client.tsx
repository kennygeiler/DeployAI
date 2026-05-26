"use client";

import { PencilIcon } from "lucide-react";
import * as React from "react";

import { TimestampLabel } from "@/components/common/TimestampLabel.client";
import { NodeEditDialog } from "@/components/engagements/NodeEditDialog.client";
import { ProvenanceTab } from "@/components/engagements/ProvenanceTab.client";
import { Button } from "@/components/ui/button";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import type { MatrixNode } from "@/lib/bff/matrix-types";
import { readStrategistBffErrorDescription } from "@/lib/bff/read-strategist-bff-error";

type CitationEvent = {
  id: string;
  occurred_at: string;
  event_type: string;
  source_ref: string | null;
  summary: string;
};

type TabKey = "source" | "provenance";

function SourceEventsList({ engagementId, ids }: { engagementId: string; ids: string[] }) {
  const [events, setEvents] = React.useState<CitationEvent[]>([]);
  const [loading, setLoading] = React.useState(false);
  const [err, setErr] = React.useState<string | null>(null);
  const idsKey = ids.join(",");

  React.useEffect(() => {
    let cancelled = false;
    void (async () => {
      if (ids.length === 0) {
        if (cancelled) return;
        setEvents([]);
        setErr(null);
        setLoading(false);
        return;
      }
      setLoading(true);
      setErr(null);
      try {
        const url =
          `/api/bff/engagements/${encodeURIComponent(engagementId)}/events` +
          `?ids=${encodeURIComponent(idsKey)}`;
        const r = await fetch(url, { cache: "no-store" });
        if (cancelled) return;
        if (!r.ok) {
          setErr(await readStrategistBffErrorDescription(r));
          setEvents([]);
          return;
        }
        const body = (await r.json()) as { events?: CitationEvent[] };
        setEvents(Array.isArray(body.events) ? body.events : []);
      } catch (e) {
        if (!cancelled) {
          setErr(e instanceof Error ? e.message : "Could not load source events.");
          setEvents([]);
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [engagementId, idsKey, ids.length]);

  if (ids.length === 0) {
    return (
      <p className="text-ink-600 text-sm">
        No source events to show — this entity has no evidence cited.
      </p>
    );
  }
  if (loading) return <p className="text-ink-600 text-sm">Loading…</p>;
  if (err) return <p className="text-error-700 text-sm">{err}</p>;
  if (events.length === 0) return <p className="text-ink-600 text-sm">No source events found.</p>;
  return (
    <ul className="border-border divide-border divide-y rounded-lg border text-sm">
      {events.map((ev) => (
        <li key={ev.id} className="space-y-1 px-3 py-2">
          <div className="flex items-center justify-between gap-3">
            <TimestampLabel value={ev.occurred_at} className="text-ink-700" />
            <span className="bg-ink-100 text-ink-800 rounded px-1.5 py-0.5 font-mono text-[10px] uppercase">
              {ev.event_type}
            </span>
          </div>
          <p className="text-ink-800 whitespace-pre-line">{ev.summary}</p>
          {ev.source_ref ? (
            <p className="text-ink-500 font-mono text-xs break-all">{ev.source_ref}</p>
          ) : null}
        </li>
      ))}
    </ul>
  );
}

export function MatrixNodeDetail({
  engagementId,
  nodeId,
  title,
  evidenceEventIds,
  open,
  onClose,
  node,
  onNodeSaved,
}: {
  engagementId: string;
  nodeId: string | null;
  title: string;
  evidenceEventIds: string[];
  open: boolean;
  onClose: () => void;
  node?: Pick<MatrixNode, "id" | "title" | "node_type" | "attributes"> | null;
  onNodeSaved?: (next: MatrixNode) => void;
}) {
  const [tab, setTab] = React.useState<TabKey>("source");
  const [lastKey, setLastKey] = React.useState<string | null>(null);
  const [editOpen, setEditOpen] = React.useState(false);
  const currentKey = open ? `${nodeId ?? ""}` : null;
  if (currentKey !== lastKey) {
    setLastKey(currentKey);
    if (currentKey !== null) setTab("source");
  }

  const description =
    evidenceEventIds.length === 0
      ? "No source events cited."
      : `${evidenceEventIds.length} cited event${evidenceEventIds.length === 1 ? "" : "s"}.`;

  const canEdit = node !== null && node !== undefined && onNodeSaved !== undefined;

  return (
    <Sheet
      open={open}
      onOpenChange={(next) => {
        if (!next) onClose();
      }}
    >
      <SheetContent
        side="right"
        className="w-full sm:max-w-md"
        aria-label="Matrix node detail"
        data-testid="matrix-node-detail"
      >
        <SheetHeader>
          <div className="flex items-start justify-between gap-2">
            <SheetTitle>{title}</SheetTitle>
            {canEdit ? (
              <Button
                variant="ghost"
                size="sm"
                aria-label="Edit node"
                data-testid="matrix-node-edit-button"
                onClick={() => setEditOpen(true)}
              >
                <PencilIcon className="h-4 w-4" />
              </Button>
            ) : null}
          </div>
          <SheetDescription>{description}</SheetDescription>
        </SheetHeader>
        <div className="space-y-3 overflow-y-auto px-4 pb-4">
          <Tabs value={tab} onValueChange={(v) => setTab(v as TabKey)} className="space-y-3">
            <TabsList>
              <TabsTrigger value="source">Source events</TabsTrigger>
              <TabsTrigger value="provenance">Provenance</TabsTrigger>
            </TabsList>
            <TabsContent value="source">
              <SourceEventsList engagementId={engagementId} ids={evidenceEventIds} />
            </TabsContent>
            <TabsContent value="provenance">
              {nodeId === null ? (
                <p className="text-ink-600 text-sm">
                  Provenance is only available for matrix nodes.
                </p>
              ) : (
                <ProvenanceTab
                  engagementId={engagementId}
                  nodeId={nodeId}
                  active={tab === "provenance"}
                />
              )}
            </TabsContent>
          </Tabs>
        </div>
      </SheetContent>
      {canEdit && node ? (
        <NodeEditDialog
          engagementId={engagementId}
          node={node}
          open={editOpen}
          onClose={() => setEditOpen(false)}
          onSaved={(next) => {
            onNodeSaved?.(next);
            setEditOpen(false);
          }}
        />
      ) : null}
    </Sheet>
  );
}
