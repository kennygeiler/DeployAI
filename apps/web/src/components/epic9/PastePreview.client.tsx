"use client";

import * as React from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { readStrategistBffErrorDescription } from "@/lib/bff/read-strategist-bff-error";
import { parseEmail } from "@/lib/parsers/email";
import { parseMeetingNotes } from "@/lib/parsers/meeting-notes";

/**
 * Sprint 2.2 — paste an interaction, see the extractor's drafts live,
 * keep/discard per draft, then commit (which runs the real /ingest →
 * /extract chain). No DB writes happen until Commit.
 */

const SOURCES = ["manual_import", "meeting_note", "email", "field_note"] as const;

const SOURCE_LABEL: Record<string, string> = {
  manual_import: "Manual import",
  meeting_note: "Meeting note",
  email: "Email",
  field_note: "Field note",
};

const INPUT_CLASS = "border-border rounded-md border px-2 py-1 text-sm";

type PreviewDraft = {
  kind: string;
  payload: Record<string, unknown>;
  rationale: string | null;
};

type DraftRow = PreviewDraft & { localId: string; kept: boolean };

function summarize(draft: PreviewDraft): string {
  const payload = draft.payload ?? {};
  if (draft.kind === "node") {
    const nodeType = typeof payload.node_type === "string" ? payload.node_type : "node";
    const title = typeof payload.title === "string" ? payload.title : "(no title)";
    return `${nodeType}: ${title}`;
  }
  if (draft.kind === "edge") {
    const edgeType = typeof payload.edge_type === "string" ? payload.edge_type : "edge";
    const fromId = typeof payload.from_node_id === "string" ? payload.from_node_id : "?";
    const toId = typeof payload.to_node_id === "string" ? payload.to_node_id : "?";
    return `${fromId.slice(0, 8)} —${edgeType.replace("_", " ")}→ ${toId.slice(0, 8)}`;
  }
  return draft.kind;
}

function buildContent(
  source: string,
  raw: string,
): { content: Record<string, unknown>; occurredAt?: string } {
  if (source === "email") {
    const { parsed } = parseEmail(raw);
    return { content: { ...parsed }, occurredAt: parsed.occurred_at };
  }
  if (source === "meeting_note") {
    const parsed = parseMeetingNotes(raw);
    return { content: { ...parsed }, occurredAt: parsed.occurred_at };
  }
  try {
    const value: unknown = JSON.parse(raw);
    if (typeof value === "object" && value !== null && !Array.isArray(value)) {
      return { content: value as Record<string, unknown> };
    }
  } catch {
    // fall through to text fallback
  }
  return { content: { text: raw } };
}

export function PastePreview({
  engagementId,
  onChanged,
}: {
  engagementId: string;
  onChanged?: () => void | Promise<void>;
}) {
  const [source, setSource] = React.useState<string>("manual_import");
  const [body, setBody] = React.useState("");
  const [previewBusy, setPreviewBusy] = React.useState(false);
  const [commitBusy, setCommitBusy] = React.useState(false);
  const [drafts, setDrafts] = React.useState<DraftRow[] | null>(null);
  const [pendingPayload, setPendingPayload] = React.useState<{
    source: string;
    occurredAt?: string;
    content: Record<string, unknown>;
  } | null>(null);

  const preview = React.useCallback(async () => {
    const raw = body.trim();
    if (!raw) {
      return;
    }
    setPreviewBusy(true);
    try {
      const { content, occurredAt } = buildContent(source, raw);
      const payload: Record<string, unknown> = { source, content };
      if (occurredAt) {
        payload.occurred_at = occurredAt;
      }
      const r = await fetch(
        `/api/bff/engagements/${encodeURIComponent(engagementId)}/extract-preview`,
        {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify(payload),
        },
      );
      if (!r.ok) {
        toast.error("Could not preview", {
          description: (await readStrategistBffErrorDescription(r)).slice(0, 240),
        });
        setDrafts(null);
        return;
      }
      const json = (await r.json()) as { drafts: PreviewDraft[] };
      const rows: DraftRow[] = json.drafts.map((d, i) => ({
        ...d,
        localId: `${i}-${d.kind}-${typeof d.payload.title === "string" ? d.payload.title : i}`,
        kept: true,
      }));
      setDrafts(rows);
      setPendingPayload({ source, occurredAt, content });
    } finally {
      setPreviewBusy(false);
    }
  }, [engagementId, source, body]);

  const toggleKeep = React.useCallback((localId: string) => {
    setDrafts((prev) =>
      prev === null ? prev : prev.map((d) => (d.localId === localId ? { ...d, kept: !d.kept } : d)),
    );
  }, []);

  const commit = React.useCallback(async () => {
    if (drafts === null || pendingPayload === null) {
      return;
    }
    const kept = drafts.filter((d) => d.kept);
    if (kept.length === 0) {
      toast.error("Keep at least one draft, or discard all and re-preview.");
      return;
    }
    setCommitBusy(true);
    try {
      const payload: Record<string, unknown> = {
        source: pendingPayload.source,
        content: pendingPayload.content,
      };
      if (pendingPayload.occurredAt) {
        payload.occurred_at = pendingPayload.occurredAt;
      }
      const r = await fetch(`/api/bff/engagements/${encodeURIComponent(engagementId)}/ingest`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!r.ok) {
        toast.error("Could not commit", {
          description: (await readStrategistBffErrorDescription(r)).slice(0, 240),
        });
        return;
      }
      // /ingest chains /extract on the CP side; the extractor produces its
      // own proposals from the same event. We do not push individual kept
      // drafts to the CP — the parent's refresh surfaces the real proposals
      // in the existing review section.
      toast.success(`Committed (kept ${kept.length} of ${drafts.length})`);
      setBody("");
      setDrafts(null);
      setPendingPayload(null);
      if (onChanged) {
        await onChanged();
      }
    } finally {
      setCommitBusy(false);
    }
  }, [engagementId, drafts, pendingPayload, onChanged]);

  return (
    <div className="border-border space-y-3 rounded-lg border p-3">
      <h3 className="text-ink-800 text-xs font-semibold">Preview before commit</h3>
      <p className="text-ink-500 text-xs">
        Paste an interaction, see the matrix entities the extractor would propose, then commit. The
        canonical event is only written when you commit — preview itself writes nothing.
      </p>
      <div className="flex flex-wrap items-end gap-2">
        <div className="grid gap-1">
          <label className="text-ink-600 text-xs" htmlFor="preview-source">
            Source
          </label>
          <select
            id="preview-source"
            className={INPUT_CLASS}
            value={source}
            onChange={(e) => setSource(e.target.value)}
          >
            {SOURCES.map((s) => (
              <option key={s} value={s}>
                {SOURCE_LABEL[s]}
              </option>
            ))}
          </select>
        </div>
        <div className="grid min-w-64 flex-1 gap-1">
          <label className="text-ink-600 text-xs" htmlFor="preview-content">
            Content (text or JSON)
          </label>
          <textarea
            id="preview-content"
            className="border-border min-h-20 rounded-md border px-2 py-1 text-sm"
            placeholder='Paste an email, a meeting summary, or {"text": "…"}'
            value={body}
            onChange={(e) => setBody(e.target.value)}
          />
        </div>
        <Button
          type="button"
          size="sm"
          disabled={previewBusy || commitBusy || !body.trim()}
          onClick={() => void preview()}
        >
          {previewBusy ? "Previewing…" : "Preview"}
        </Button>
      </div>

      {drafts !== null ? (
        <div className="space-y-2">
          <p className="text-ink-700 text-xs font-medium">
            {drafts.length === 0
              ? "No drafts — the extractor found nothing to propose."
              : `${drafts.filter((d) => d.kept).length} of ${drafts.length} draft(s) kept`}
          </p>
          {drafts.length > 0 ? (
            <ul
              className="border-border divide-border divide-y rounded-lg border text-sm"
              aria-label="Preview drafts"
            >
              {drafts.map((d) => (
                <li key={d.localId} className="flex items-start justify-between gap-3 px-3 py-2">
                  <div className="flex-1 space-y-0.5">
                    <p className={d.kept ? "text-ink-800" : "text-ink-400 line-through"}>
                      <span className="text-ink-600 mr-2 font-mono text-xs uppercase">
                        {d.kind}
                      </span>
                      {summarize(d)}
                    </p>
                    {d.rationale ? (
                      <p className="text-ink-500 text-xs">{d.rationale}</p>
                    ) : (
                      <p className="text-ink-400 text-xs italic">(no rationale)</p>
                    )}
                  </div>
                  <Button
                    type="button"
                    size="sm"
                    variant={d.kept ? "outline" : "default"}
                    className="h-7 px-2 text-xs"
                    onClick={() => toggleKeep(d.localId)}
                  >
                    {d.kept ? "Discard" : "Keep"}
                  </Button>
                </li>
              ))}
            </ul>
          ) : null}
          <div className="flex justify-end">
            <Button
              type="button"
              size="sm"
              disabled={commitBusy || previewBusy || drafts.filter((d) => d.kept).length === 0}
              onClick={() => void commit()}
            >
              {commitBusy ? "Committing…" : "Commit all kept"}
            </Button>
          </div>
        </div>
      ) : null}
    </div>
  );
}
