/**
 * Phase 6 (increment 6.3.1) — raw-email parser for the paste-import surface.
 *
 * Accepts a pasted email in RFC-822-ish shape (headers, blank line, body)
 * OR a plain text blob that *starts* with "From: ..." / "Subject: ..." lines,
 * which is what most people paste from Gmail, Outlook, Apple Mail, etc.
 *
 * Returns a normalized `ParsedEmail` with the body as `text` (the field
 * the Cartographer extraction agent reads) plus structured headers as
 * additional keys. Falls back to `{text: raw}` when no headers detected
 * so a totally unstructured paste still imports cleanly.
 *
 * Out of scope: MIME multipart, quoted-printable decoding, attachments,
 * thread-context extraction. Real email harnesses (6.3.3 Gmail OAuth)
 * will replace this with provider-side parsing.
 */

export type ParsedEmail = {
  text: string;
  subject?: string;
  from?: string;
  to?: string;
  cc?: string;
  date?: string;
  occurred_at?: string; // ISO 8601 if Date header parseable
};

// Header keys we extract. Case-insensitive match; later occurrences win.
const HEADERS = ["from", "to", "cc", "subject", "date"] as const;

/**
 * Parse a pasted email. Always returns a value — body is always preserved.
 * Returns `headerCount` so callers can decide whether parsing was useful
 * (zero = blob is just text; ignore the extracted headers).
 */
export function parseEmail(raw: string): { parsed: ParsedEmail; headerCount: number } {
  const trimmed = raw.replace(/^﻿/, ""); // strip BOM
  const lines = trimmed.split(/\r?\n/);

  const headers: Record<string, string> = {};
  let bodyStart = 0;
  let inHeaders = true;
  let lastHeaderKey: string | null = null;

  for (let i = 0; i < lines.length; i += 1) {
    const line = lines[i] ?? "";
    if (inHeaders && line.trim() === "") {
      // Blank line ends headers — only if we found at least one header,
      // otherwise the blank line might just be inside the body of a
      // header-less paste.
      if (Object.keys(headers).length > 0) {
        bodyStart = i + 1;
        inHeaders = false;
        break;
      }
      // Otherwise: no headers at all, the whole blob is body.
      bodyStart = 0;
      inHeaders = false;
      break;
    }
    if (!inHeaders) {
      break;
    }
    // Header continuation lines start with whitespace.
    if (/^[ \t]/.test(line) && lastHeaderKey) {
      headers[lastHeaderKey] = `${headers[lastHeaderKey] ?? ""} ${line.trim()}`;
      continue;
    }
    const m = /^([A-Za-z][A-Za-z0-9-]*)\s*:\s*(.*)$/.exec(line);
    if (m && m[1]) {
      const key = m[1].toLowerCase();
      const value = m[2] ?? "";
      if ((HEADERS as readonly string[]).includes(key)) {
        headers[key] = value.trim();
        lastHeaderKey = key;
      } else {
        // Unknown header — track it but don't surface it; still extends
        // the header block.
        lastHeaderKey = null;
      }
      continue;
    }
    // Not a header line and not a continuation — first line of body.
    bodyStart = i;
    inHeaders = false;
    break;
  }

  const bodyLines = lines.slice(bodyStart);
  // Trim a single leading blank line if present (cosmetic).
  if (bodyLines[0] === "") {
    bodyLines.shift();
  }
  const body = bodyLines.join("\n").trim();

  const parsed: ParsedEmail = { text: body || trimmed };
  for (const key of HEADERS) {
    const v = headers[key];
    if (v) {
      parsed[key] = v;
    }
  }
  // Try to parse the Date header into an ISO 8601 string. Date.parse is
  // generous (accepts RFC 2822, ISO, etc.); if it fails, leave undefined.
  if (parsed.date) {
    const ms = Date.parse(parsed.date);
    if (!Number.isNaN(ms)) {
      parsed.occurred_at = new Date(ms).toISOString();
    }
  }
  return { parsed, headerCount: Object.keys(headers).length };
}
