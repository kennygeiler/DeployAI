/**
 * Wave 5 IN3 — naive .eml → paste-box text for the Capture surface.
 *
 * Treats the file as text: the RFC-822 header block (everything up to the
 * first blank line) is stripped, except Subject/From/Date which are kept as
 * a prefix so the Cartographer extractor sees who/when. Header continuation
 * lines (leading whitespace) fold into the previous header.
 *
 * Out of scope, on purpose (same posture as `parsers/email.ts`): MIME
 * multipart selection, base64/quoted-printable decoding, attachments —
 * the body is passed through verbatim, so an HTML-only or base64-encoded
 * .eml pastes as its raw part text. Server-side intake (docs/ops/
 * intake-email.md) is the robust path for real mail.
 */

const KEPT_HEADERS = ["subject", "from", "date"] as const;

export function emlToText(raw: string): string {
  const lines = raw.replace(/^﻿/, "").split(/\r?\n/);

  const kept: Partial<Record<(typeof KEPT_HEADERS)[number], string>> = {};
  let bodyStart = lines.length;
  let lastKey: string | null = null;
  let sawHeader = false;

  for (let i = 0; i < lines.length; i += 1) {
    const line = lines[i] ?? "";
    if (line.trim() === "") {
      // First blank line ends the header block. A file with no header-shaped
      // first line at all is treated as body from the top (handled below).
      bodyStart = i + 1;
      break;
    }
    const continuation = /^[ \t]/.test(line) && lastKey !== null;
    if (continuation) {
      if (lastKey && (KEPT_HEADERS as readonly string[]).includes(lastKey)) {
        const k = lastKey as (typeof KEPT_HEADERS)[number];
        kept[k] = `${kept[k] ?? ""} ${line.trim()}`.trim();
      }
      continue;
    }
    const m = line.match(/^([A-Za-z][A-Za-z0-9-]*):\s?(.*)$/);
    if (!m) {
      // Not header-shaped: this isn't an RFC-822 header block — return the
      // whole file untouched rather than eating lines that were body.
      if (!sawHeader) {
        return raw;
      }
      lastKey = null;
      continue;
    }
    sawHeader = true;
    const key = m[1]!.toLowerCase();
    lastKey = key;
    if ((KEPT_HEADERS as readonly string[]).includes(key)) {
      kept[key as (typeof KEPT_HEADERS)[number]] = m[2] ?? "";
    }
  }

  const body = lines.slice(bodyStart).join("\n").trim();
  const prefix = KEPT_HEADERS.filter((k) => (kept[k] ?? "").trim() !== "")
    .map((k) => `${k[0]!.toUpperCase()}${k.slice(1)}: ${kept[k]!.trim()}`)
    .join("\n");
  if (!prefix) {
    return body;
  }
  return body ? `${prefix}\n\n${body}` : prefix;
}
