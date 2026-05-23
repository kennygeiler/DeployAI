/**
 * Phase 6 (increment 6.3.2) — meeting-notes / transcript parser for the
 * paste-import surface. Auto-detects common formats:
 *
 *   - Otter / Fireflies: "[Speaker Name 00:01:23] words..." per line
 *   - Granola: a header date + sections of bulleted lines
 *   - Plain notes: any unstructured paste falls back to {text: raw}
 *
 * Returns a normalized `ParsedMeetingNotes` with the cleaned text body
 * (the field Cartographer reads), plus best-effort `title`, `participants`,
 * and `occurred_at` when the format leaks them.
 *
 * Out of scope: speaker diarization beyond name extraction, agenda
 * mapping, action-item extraction (Cartographer does that downstream).
 */

export type ParsedMeetingNotes = {
  text: string;
  title?: string;
  participants?: string[];
  occurred_at?: string; // ISO 8601
  format: "otter" | "granola" | "plain";
};

const OTTER_LINE = /^\[?([A-Z][\w '.-]+?)\s+(\d{1,2}:\d{2}(?::\d{2})?)\]?\s*[:\-]?\s*(.*)$/;
const GRANOLA_HEADING = /^#{1,3}\s+(.+?)$/;
const ISO_DATE_GUESS = /\b(\d{4})-(\d{2})-(\d{2})(?:[T ](\d{2}):(\d{2}))?\b/;

export function parseMeetingNotes(raw: string): ParsedMeetingNotes {
  const trimmed = raw.replace(/^﻿/, "").trim();
  if (!trimmed) {
    return { text: "", format: "plain" };
  }

  const lines = trimmed.split(/\r?\n/);

  // Format detection: count lines that look Otter-shaped.
  let otterLikeLines = 0;
  let markdownHeadingCount = 0;
  for (const line of lines) {
    if (OTTER_LINE.test(line)) {
      otterLikeLines += 1;
    }
    if (GRANOLA_HEADING.test(line)) {
      markdownHeadingCount += 1;
    }
  }

  if (otterLikeLines >= 3 && otterLikeLines / lines.length >= 0.3) {
    return parseOtterStyle(lines, trimmed);
  }
  if (markdownHeadingCount >= 1) {
    return parseGranolaStyle(lines, trimmed);
  }
  return { text: trimmed, format: "plain", occurred_at: extractDate(trimmed) };
}

function parseOtterStyle(lines: string[], raw: string): ParsedMeetingNotes {
  const participants = new Set<string>();
  const out: string[] = [];
  for (const line of lines) {
    const m = OTTER_LINE.exec(line);
    if (m && m[1] && m[3] !== undefined) {
      const speaker = m[1].trim();
      const utterance = m[3].trim();
      if (speaker) {
        participants.add(speaker);
      }
      if (utterance) {
        out.push(`${speaker}: ${utterance}`);
      }
    } else if (line.trim()) {
      out.push(line.trim());
    }
  }
  return {
    text: out.join("\n"),
    participants: [...participants],
    occurred_at: extractDate(raw),
    format: "otter",
  };
}

function parseGranolaStyle(lines: string[], raw: string): ParsedMeetingNotes {
  let title: string | undefined;
  for (const line of lines) {
    const m = GRANOLA_HEADING.exec(line);
    if (m && m[1]) {
      title = m[1].trim();
      break;
    }
  }
  // Granola uses markdown bullet points; strip leading dashes for readability
  // but preserve the structure as visible text.
  const text = lines
    .map((l) => l.replace(/^[-*+]\s+/, "• "))
    .join("\n")
    .trim();
  return {
    text,
    title,
    occurred_at: extractDate(raw),
    format: "granola",
  };
}

/**
 * Try to find a date anywhere in the raw text. ISO 8601 first, then a few
 * common forms. Returns ISO 8601 or undefined.
 */
function extractDate(raw: string): string | undefined {
  const iso = ISO_DATE_GUESS.exec(raw);
  if (iso && iso[1] && iso[2] && iso[3]) {
    const year = iso[1];
    const month = iso[2];
    const day = iso[3];
    const hour = iso[4] ?? "00";
    const minute = iso[5] ?? "00";
    const iso8601 = `${year}-${month}-${day}T${hour}:${minute}:00Z`;
    const ms = Date.parse(iso8601);
    if (!Number.isNaN(ms)) {
      return new Date(ms).toISOString();
    }
  }
  return undefined;
}
