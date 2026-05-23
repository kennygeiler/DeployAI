import { describe, expect, it } from "vitest";

import { parseMeetingNotes } from "./meeting-notes";

describe("parseMeetingNotes", () => {
  it("detects Otter-style transcripts and surfaces participants", () => {
    const raw =
      "[Dana Carter 00:00:01] Welcome everyone.\n" +
      "[Priya Raman 00:00:14] Thanks Dana.\n" +
      "[Marcus Okafor 00:01:02] Quick update on the vendor selection.\n" +
      "[Dana Carter 00:01:30] Go ahead.";
    const result = parseMeetingNotes(raw);
    expect(result.format).toBe("otter");
    expect(result.participants?.sort()).toEqual(["Dana Carter", "Marcus Okafor", "Priya Raman"]);
    expect(result.text).toContain("Dana Carter: Welcome everyone.");
    expect(result.text).toContain("Marcus Okafor: Quick update on the vendor selection.");
  });

  it("detects Granola-style markdown notes and extracts the title", () => {
    const raw =
      "# Pilot kickoff — 2026-03-23\n\n" +
      "## Attendees\n- Dana\n- Priya\n\n" +
      "## Decisions\n- 90-day pilot scope locked\n- US-East-1 only";
    const result = parseMeetingNotes(raw);
    expect(result.format).toBe("granola");
    expect(result.title).toBe("Pilot kickoff — 2026-03-23");
    expect(result.text).toContain("• Dana");
    expect(result.text).toContain("• 90-day pilot scope locked");
    expect(result.occurred_at).toBe("2026-03-23T00:00:00.000Z");
  });

  it("falls back to plain text when no format markers are present", () => {
    const raw = "Just freeform notes about today's call.\nNothing structured.";
    const result = parseMeetingNotes(raw);
    expect(result.format).toBe("plain");
    expect(result.text).toBe(raw.trim());
    expect(result.participants).toBeUndefined();
    expect(result.title).toBeUndefined();
  });

  it("extracts ISO date from a plain paste when present in the body", () => {
    const raw = "Met with Priya on 2026-04-13T15:00 to discuss the pilot extension.";
    const result = parseMeetingNotes(raw);
    expect(result.format).toBe("plain");
    expect(result.occurred_at).toBe("2026-04-13T15:00:00.000Z");
  });

  it("returns empty text for blank input", () => {
    const result = parseMeetingNotes("   \n   \n");
    expect(result.text).toBe("");
    expect(result.format).toBe("plain");
  });

  it("preserves non-Otter lines mixed inside an Otter-style transcript", () => {
    const raw =
      "[Dana 00:00:01] Hi.\n" +
      "[Priya 00:00:05] Hi back.\n" +
      "[Dana 00:00:10] One sec.\n" +
      "(background noise)\n" +
      "[Dana 00:00:14] OK.";
    const result = parseMeetingNotes(raw);
    expect(result.format).toBe("otter");
    expect(result.text).toContain("(background noise)");
  });
});
