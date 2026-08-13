"use client";

import * as React from "react";
import { toast } from "sonner";

import { PastePreview } from "@/components/epic9/PastePreview.client";
import { IntakeAddressBlock } from "@/components/engagements/capture/IntakeAddress.client";
import { Button } from "@/components/ui/button";
import { PixelLoader } from "@/components/ui/shimmer";
import type { MatrixProposal } from "@/lib/bff/matrix-types";
import { readStrategistBffErrorDescription } from "@/lib/bff/read-strategist-bff-error";
import { parseEmail } from "@/lib/parsers/email";
import { emlToText } from "@/lib/parsers/eml";
import { parseMeetingNotes } from "@/lib/parsers/meeting-notes";
import { subtitlesToText } from "@/lib/parsers/subtitles";

const SOURCES = ["email", "meeting_note", "manual_import", "field_note"] as const;

const SOURCE_LABEL: Record<string, string> = {
  email: "Email",
  meeting_note: "Meeting note",
  manual_import: "Manual import",
  field_note: "Field note",
};

/** The demo's stated turnaround budget — shown so the wait is honest. */
const EXTRACT_HINT = "usually 10–25s";

/** File types the picker/drop accepts (IN3). All are read as text client-side. */
const ACCEPTED_FILE_TYPES = ".txt,.eml,.vtt,.srt,.md,text/plain";

/**
 * Convert a picked/dropped file's text by extension: .eml keeps
 * Subject/From/Date and strips the rest of the headers, .vtt/.srt strip cue
 * timing machinery, .txt/.md (and anything unknown) pass through as-is.
 */
function fileTextToPaste(fileName: string, text: string): string {
  const ext = fileName.toLowerCase().match(/\.([a-z0-9]+)$/)?.[1] ?? "";
  if (ext === "eml") {
    return emlToText(text);
  }
  if (ext === "vtt" || ext === "srt") {
    return subtitlesToText(text);
  }
  return text;
}

type Phase =
  | { name: "idle" }
  | { name: "saving" }
  | { name: "extracting" }
  | { name: "done"; proposalCount: number }
  | { name: "error"; message: string };

/** Format a paste-time local Date as a datetime-local input value. */
function toDatetimeLocalValue(d: Date): string {
  const pad = (n: number) => String(n).padStart(2, "0");
  return (
    `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}` +
    `T${pad(d.getHours())}:${pad(d.getMinutes())}`
  );
}

/** Build the ingest content payload, reusing the source-aware parsers. */
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
    // plain text — fall through
  }
  return { content: { text: raw } };
}

/**
 * Wave 3 K2 — the Capture tab's ingestion surface.
 *
 * One large paste box (email thread / meeting notes / Slack excerpt), a
 * source-type select, an occurred-at picker defaulting to now, and drag-drop
 * or file-pick of a .txt/.md/.eml/.vtt/.srt that lands in the same box
 * (converted to plain text client-side — see `fileTextToPaste`). Below the
 * paste card, the IN2 intake-address block offers the CC-a-deal-address
 * alternative. Submit runs the staged
 * flow — POST /ingest with `extract: false`, then POST /extract — so the
 * progress line can say what is actually happening: "Saving…" →
 * "Extracting ({EXTRACT_HINT})…" with a live elapsed counter → "N proposals
 * ready — review below" (scrolls to the Needs-you queue), or an honest
 * error / no-proposals state.
 *
 * `data-tour="capture-input"` on the textarea wrapper is the guided tour's
 * spotlight target for the capture act.
 */
export function CaptureIngest({
  engagementId,
  onChanged,
}: {
  engagementId: string;
  onChanged?: () => void | Promise<void>;
}) {
  const [source, setSource] = React.useState<string>("email");
  const [body, setBody] = React.useState("");
  const [occurredAt, setOccurredAt] = React.useState<string>(() =>
    toDatetimeLocalValue(new Date()),
  );
  const [phase, setPhase] = React.useState<Phase>({ name: "idle" });
  const [dragging, setDragging] = React.useState(false);
  const [previewMode, setPreviewMode] = React.useState(false);
  const fileInputRef = React.useRef<HTMLInputElement>(null);

  const busy = phase.name === "saving" || phase.name === "extracting";

  const readFile = React.useCallback(async (file: File) => {
    try {
      // FileReader over File.text(): identical result, and it exists in
      // every environment the tests run in (jsdom lacks Blob.text()).
      const text = await new Promise<string>((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => resolve(String(reader.result ?? ""));
        reader.onerror = () => reject(reader.error ?? new Error("read failed"));
        reader.readAsText(file);
      });
      setBody(fileTextToPaste(file.name, text));
      setPhase({ name: "idle" });
      toast.success(`Loaded ${file.name}`, { description: "Review the text, then Capture it." });
    } catch {
      toast.error(`Could not read ${file.name}`);
    }
  }, []);

  const onDrop = React.useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setDragging(false);
      const file = e.dataTransfer.files?.[0];
      if (file) {
        void readFile(file);
      }
    },
    [readFile],
  );

  const submit = React.useCallback(async () => {
    const raw = body.trim();
    if (!raw) {
      return;
    }
    setPhase({ name: "saving" });
    try {
      const { content, occurredAt: parsedOccurredAt } = buildContent(source, raw);
      // Priority: a timestamp parsed out of the paste itself (email Date
      // header, meeting-note date) beats the form field, which defaults to
      // "now" — the moment of capture.
      const occurredAtIso =
        parsedOccurredAt ??
        (occurredAt ? new Date(occurredAt).toISOString() : new Date().toISOString());

      const ingestRes = await fetch(
        `/api/bff/engagements/${encodeURIComponent(engagementId)}/ingest`,
        {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({ source, content, occurred_at: occurredAtIso, extract: false }),
        },
      );
      if (!ingestRes.ok) {
        setPhase({
          name: "error",
          message: `Could not save the interaction: ${(await readStrategistBffErrorDescription(ingestRes)).slice(0, 240)}`,
        });
        return;
      }
      const { event } = (await ingestRes.json()) as { event: { id: string } };

      setPhase({ name: "extracting" });
      const extractRes = await fetch(
        `/api/bff/engagements/${encodeURIComponent(engagementId)}/extract`,
        {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({ event_id: event.id }),
        },
      );
      if (!extractRes.ok) {
        setPhase({
          name: "error",
          message:
            "Saved — but extraction failed: " +
            `${(await readStrategistBffErrorDescription(extractRes)).slice(0, 240)}. ` +
            "The interaction is recorded; extraction can be retried.",
        });
        return;
      }
      const { proposals } = (await extractRes.json()) as { proposals: MatrixProposal[] };
      const pending = proposals.filter((p) => p.status === "pending").length;
      setBody("");
      setPhase({ name: "done", proposalCount: pending });
      if (onChanged) {
        await onChanged();
      }
      if (pending > 0) {
        // Give the refreshed proposals a beat to render, then bring the
        // human gate into view — that's where the demo goes next.
        window.setTimeout(() => {
          document
            .querySelector('[data-tour="brief-needs-you"]')
            ?.scrollIntoView({ behavior: "smooth", block: "start" });
        }, 250);
      }
    } catch (e) {
      setPhase({
        name: "error",
        message: e instanceof Error ? e.message : "Something went wrong — try again.",
      });
    }
  }, [engagementId, source, body, occurredAt, onChanged]);

  return (
    <div className="space-y-2">
      <label className="text-ink-600 flex items-center gap-2 text-xs">
        <input
          type="checkbox"
          checked={previewMode}
          onChange={(e) => setPreviewMode(e.target.checked)}
          aria-label="Preview before commit"
        />
        Preview before commit
      </label>
      {previewMode ? (
        <PastePreview engagementId={engagementId} onChanged={onChanged} />
      ) : (
        <div
          className={
            "space-y-3 rounded-card bg-surface p-3 shadow-card" +
            (dragging ? " ring-2 ring-ring/50" : "")
          }
          onDragOver={(e) => {
            e.preventDefault();
            setDragging(true);
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={onDrop}
          data-testid="capture-dropzone"
        >
          <div data-tour="capture-input" className="grid gap-1">
            <label className="text-ink-600 text-xs" htmlFor="capture-content">
              Interaction
            </label>
            <textarea
              id="capture-content"
              className="min-h-40 rounded-control border border-transparent bg-field px-2 py-1.5 font-mono text-xs shadow-inset-field outline-none focus-visible:ring-2 focus-visible:ring-ring/50"
              placeholder="Paste an email thread, meeting notes, or a Slack excerpt — or drop a .txt, .md, .eml, .vtt or .srt file here"
              value={body}
              onChange={(e) => setBody(e.target.value)}
              disabled={busy}
            />
          </div>
          <div className="flex flex-wrap items-end gap-3">
            <div className="grid gap-1">
              <label className="text-ink-600 text-xs" htmlFor="capture-source">
                Source
              </label>
              <select
                id="capture-source"
                className="rounded-control border border-transparent bg-field px-2 py-1 text-sm shadow-inset-field outline-none focus-visible:ring-2 focus-visible:ring-ring/50"
                value={source}
                onChange={(e) => setSource(e.target.value)}
                disabled={busy}
              >
                {SOURCES.map((s) => (
                  <option key={s} value={s}>
                    {SOURCE_LABEL[s]}
                  </option>
                ))}
              </select>
            </div>
            <div className="grid gap-1">
              <label className="text-ink-600 text-xs" htmlFor="capture-occurred-at">
                When it happened
              </label>
              <input
                id="capture-occurred-at"
                type="datetime-local"
                className="rounded-control border border-transparent bg-field px-2 py-1 text-sm shadow-inset-field outline-none focus-visible:ring-2 focus-visible:ring-ring/50"
                value={occurredAt}
                onChange={(e) => setOccurredAt(e.target.value)}
                disabled={busy}
              />
            </div>
            <input
              ref={fileInputRef}
              type="file"
              accept={ACCEPTED_FILE_TYPES}
              className="sr-only"
              aria-label="Pick a file"
              onChange={(e) => {
                const file = e.target.files?.[0];
                if (file) {
                  void readFile(file);
                }
                e.target.value = "";
              }}
            />
            <Button
              type="button"
              size="sm"
              variant="outline"
              disabled={busy}
              onClick={() => fileInputRef.current?.click()}
            >
              Pick a file
            </Button>
            <Button
              type="button"
              size="sm"
              disabled={busy || !body.trim()}
              onClick={() => void submit()}
            >
              Capture
            </Button>
          </div>

          <div aria-live="polite" data-testid="capture-status">
            {phase.name === "saving" ? <PixelLoader label="Saving" showElapsed={false} /> : null}
            {phase.name === "extracting" ? (
              <PixelLoader label={`Extracting (${EXTRACT_HINT})`} />
            ) : null}
            {phase.name === "done" ? (
              phase.proposalCount > 0 ? (
                <p className="text-sm font-medium text-green-ink">
                  {phase.proposalCount} proposal{phase.proposalCount === 1 ? "" : "s"} ready —
                  review below in Needs&nbsp;you.
                </p>
              ) : (
                <p className="text-ink-600 text-sm">
                  Captured — but extraction found no proposals in this text. The interaction is on
                  the record; try a richer excerpt (decisions, commitments, named people).
                </p>
              )
            ) : null}
            {phase.name === "error" ? (
              <p className="text-destructive text-sm">{phase.message}</p>
            ) : null}
          </div>
        </div>
      )}
      <IntakeAddressBlock engagementId={engagementId} />
    </div>
  );
}
