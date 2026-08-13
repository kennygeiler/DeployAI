/**
 * Wave 5 IN3 — naive .vtt / .srt → plain transcript text for Capture.
 *
 * Drops the machinery (WEBVTT preamble, NOTE/STYLE/REGION blocks, cue
 * sequence numbers, `-->` timing lines) and inline VTT voice/formatting
 * tags, keeping speaker names from `<v Speaker>` tags as a "Speaker:"
 * prefix. Consecutive cue lines join with newlines; blank lines collapse.
 *
 * Not a spec-complete parser — malformed cues degrade to their raw text
 * rather than erroring, which is the right failure mode for a paste box.
 */

const TIMING_RE = /-->/;
const SEQUENCE_RE = /^\d+$/;
const VOICE_TAG_RE = /<v(?:\.[^ >]*)?\s+([^>]*)>/i;
const INLINE_TAG_RE = /<\/?[^>]+>/g;

export function subtitlesToText(raw: string): string {
  const lines = raw.replace(/^﻿/, "").split(/\r?\n/);
  const out: string[] = [];
  let skippingBlock = false;

  for (const line of lines) {
    const t = line.trim();
    if (skippingBlock) {
      if (t === "") {
        skippingBlock = false;
      }
      continue;
    }
    if (t === "") {
      if (out.length > 0 && out[out.length - 1] !== "") {
        out.push("");
      }
      continue;
    }
    if (/^WEBVTT/i.test(t)) {
      continue;
    }
    if (/^(NOTE|STYLE|REGION)\b/.test(t)) {
      skippingBlock = true;
      continue;
    }
    if (TIMING_RE.test(t) || SEQUENCE_RE.test(t)) {
      continue;
    }
    const voice = t.match(VOICE_TAG_RE);
    const speaker = voice?.[1]?.trim();
    let text = t.replace(INLINE_TAG_RE, "").trim();
    if (speaker && text) {
      text = `${speaker}: ${text}`;
    }
    if (text) {
      out.push(text);
    }
  }
  // Trim leading/trailing blank separators.
  while (out[0] === "") {
    out.shift();
  }
  while (out[out.length - 1] === "") {
    out.pop();
  }
  return out.join("\n");
}
