import { emlToText } from "@/lib/parsers/eml";
import { subtitlesToText } from "@/lib/parsers/subtitles";

/**
 * Convert a picked/dropped file's text by extension: .eml keeps
 * Subject/From/Date and strips the rest of the headers, .vtt/.srt strip cue
 * timing machinery, .txt/.md (and anything unknown) pass through as-is.
 *
 * Shared between CaptureIngest's drop/pick path and the tour's one-click
 * attach button (tour-ux) so both land the SAME text in the paste box —
 * `name` can be a file name or a URL path; only the trailing extension
 * matters.
 */
export function fileTextToPaste(name: string, text: string): string {
  const ext = name.toLowerCase().match(/\.([a-z0-9]+)$/)?.[1] ?? "";
  if (ext === "eml") {
    return emlToText(text);
  }
  if (ext === "vtt" || ext === "srt") {
    return subtitlesToText(text);
  }
  return text;
}
