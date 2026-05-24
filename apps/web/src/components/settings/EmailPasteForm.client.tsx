"use client";

import * as React from "react";
import { toast } from "sonner";
import { z } from "zod";

import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  EMAIL_PASTE_SOURCES,
  type EmailPasteSource,
  zEmailIngestEvent,
} from "@/lib/internal/emails-cp";

const SOURCE_LABELS: Record<EmailPasteSource, string> = {
  imap_paste: "IMAP — single message (RFC 5322)",
  mbox_paste: "MBOX — one or more messages",
  manual_paste: "Manual paste (single message)",
};

const zResponse = z.object({ events: z.array(zEmailIngestEvent) });

export function EmailPasteForm() {
  const [source, setSource] = React.useState<EmailPasteSource>("imap_paste");
  const [raw, setRaw] = React.useState("");
  const [submitting, setSubmitting] = React.useState(false);
  const [lastCount, setLastCount] = React.useState<number | null>(null);
  const [err, setErr] = React.useState<string | null>(null);

  const onSubmit = React.useCallback(
    async (e: React.FormEvent) => {
      e.preventDefault();
      const body = raw.trim();
      if (!body) {
        setErr("Paste a message before submitting.");
        return;
      }
      setSubmitting(true);
      setErr(null);
      try {
        const r = await fetch("/api/bff/tenant/emails/ingest", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ source, raw: body }),
        });
        if (!r.ok) {
          const text = await r.text();
          setErr(text.slice(0, 240) || `Request failed (${r.status})`);
          toast.error("Could not import email", { description: text.slice(0, 240) });
          return;
        }
        const parsed = zResponse.safeParse(await r.json());
        if (!parsed.success) {
          setErr("Could not parse server response.");
          return;
        }
        setLastCount(parsed.data.events.length);
        setRaw("");
        toast.success(
          `Imported ${parsed.data.events.length} message${parsed.data.events.length === 1 ? "" : "s"}`,
        );
      } catch (e2) {
        const msg = e2 instanceof Error ? e2.message : "Could not import email.";
        setErr(msg);
      } finally {
        setSubmitting(false);
      }
    },
    [source, raw],
  );

  return (
    <section aria-labelledby="email-import-heading" className="max-w-3xl space-y-4">
      <div>
        <h2 id="email-import-heading" className="text-base font-semibold">
          Email paste-import
        </h2>
        <p className="text-ink-600 mt-1 text-sm">
          Paste a raw email (RFC 5322) or an mbox export to land it in the engagement&apos;s ingest
          queue. OAuth-delivered Gmail/M365 will replace this path later.
        </p>
      </div>
      <form onSubmit={onSubmit} className="space-y-4">
        <div className="space-y-2">
          <Label htmlFor="email-source">Source</Label>
          <select
            id="email-source"
            value={source}
            onChange={(e) => setSource(e.target.value as EmailPasteSource)}
            className="border-input bg-bg focus-visible:ring-ring/50 h-9 w-full rounded-md border px-3 text-sm shadow-xs focus-visible:ring-[3px]"
          >
            {EMAIL_PASTE_SOURCES.map((s) => (
              <option key={s} value={s}>
                {SOURCE_LABELS[s]}
              </option>
            ))}
          </select>
        </div>
        <div className="space-y-2">
          <Label htmlFor="email-raw">Raw message</Label>
          <Textarea
            id="email-raw"
            value={raw}
            onChange={(e) => setRaw(e.target.value)}
            placeholder="Message-ID: <...>\nFrom: ...\nTo: ...\nSubject: ...\n\nbody"
            rows={12}
            required
            className="font-mono text-xs"
          />
        </div>
        {err ? <p className="text-error-700 text-sm">{err}</p> : null}
        {lastCount !== null ? (
          <p className="text-ink-600 text-sm">
            Imported {lastCount} message{lastCount === 1 ? "" : "s"} on the most recent submit.
          </p>
        ) : null}
        <Button type="submit" disabled={submitting}>
          {submitting ? "Importing…" : "Import"}
        </Button>
      </form>
    </section>
  );
}
