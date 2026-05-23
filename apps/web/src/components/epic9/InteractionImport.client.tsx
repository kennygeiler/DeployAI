"use client";

import * as React from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { readStrategistBffErrorDescription } from "@/lib/bff/read-strategist-bff-error";

const SOURCES = ["manual_import", "meeting_note", "email", "field_note"] as const;

const SOURCE_LABEL: Record<string, string> = {
  manual_import: "Manual import",
  meeting_note: "Meeting note",
  email: "Email",
  field_note: "Field note",
};

const INPUT_CLASS = "border-border rounded-md border px-2 py-1 text-sm";

/**
 * Phase 6 — universal one-shot interaction import. Posts a single
 * interaction (raw text or JSON) to the engagement; the control plane
 * records it as a canonical event. The matrix-extraction agent (Phase 6.2)
 * reads these events and proposes matrix entities citing them.
 */
export function InteractionImport({
  engagementId,
  onChanged,
}: {
  engagementId: string;
  onChanged?: () => void | Promise<void>;
}) {
  const [source, setSource] = React.useState<string>("manual_import");
  const [body, setBody] = React.useState("");
  const [busy, setBusy] = React.useState(false);

  const submit = React.useCallback(async () => {
    const raw = body.trim();
    if (!raw) {
      return;
    }
    setBusy(true);
    try {
      let content: Record<string, unknown>;
      try {
        const value: unknown = JSON.parse(raw);
        content =
          typeof value === "object" && value !== null && !Array.isArray(value)
            ? (value as Record<string, unknown>)
            : { text: raw };
      } catch {
        content = { text: raw };
      }
      const r = await fetch(`/api/bff/engagements/${encodeURIComponent(engagementId)}/ingest`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ source, content }),
      });
      if (!r.ok) {
        toast.error("Could not import interaction", {
          description: (await readStrategistBffErrorDescription(r)).slice(0, 240),
        });
        return;
      }
      toast.success("Interaction imported");
      setBody("");
      if (onChanged) {
        await onChanged();
      }
    } finally {
      setBusy(false);
    }
  }, [engagementId, source, body, onChanged]);

  return (
    <div className="border-border space-y-2 rounded-lg border p-3">
      <h3 className="text-ink-800 text-xs font-semibold">Import an interaction</h3>
      <p className="text-ink-500 text-xs">
        Paste raw text or a JSON object. The matrix-extraction agent (Phase 6.2) will read it and
        propose matrix entities citing this event.
      </p>
      <div className="flex flex-wrap items-end gap-2">
        <div className="grid gap-1">
          <label className="text-ink-600 text-xs" htmlFor="ingest-source">
            Source
          </label>
          <select
            id="ingest-source"
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
          <label className="text-ink-600 text-xs" htmlFor="ingest-content">
            Content (text or JSON)
          </label>
          <textarea
            id="ingest-content"
            className="border-border min-h-20 rounded-md border px-2 py-1 text-sm"
            placeholder='Paste an email, a meeting summary, or {"text": "…"}'
            value={body}
            onChange={(e) => setBody(e.target.value)}
          />
        </div>
        <Button
          type="button"
          size="sm"
          disabled={busy || !body.trim()}
          onClick={() => void submit()}
        >
          Import
        </Button>
      </div>
    </div>
  );
}
