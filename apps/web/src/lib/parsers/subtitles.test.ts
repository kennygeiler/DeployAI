import { describe, expect, it } from "vitest";

import { subtitlesToText } from "./subtitles";

describe("subtitlesToText", () => {
  it("strips WEBVTT preamble, timings and voice tags, keeping speakers", () => {
    const vtt = [
      "WEBVTT",
      "",
      "NOTE this block is dropped",
      "entirely",
      "",
      "1",
      "00:00:01.000 --> 00:00:03.000 align:start",
      "<v Priya>Calibration is <b>done</b>.",
      "",
      "00:00:04.000 --> 00:00:06.000",
      "Ship it Thursday.",
    ].join("\n");
    expect(subtitlesToText(vtt)).toBe("Priya: Calibration is done.\n\nShip it Thursday.");
  });

  it("strips SRT sequence numbers and comma-millisecond timings", () => {
    const srt = [
      "1",
      "00:00:01,000 --> 00:00:03,000",
      "First line.",
      "Second line of the same cue.",
      "",
      "2",
      "00:00:04,000 --> 00:00:06,000",
      "Next cue.",
    ].join("\n");
    expect(subtitlesToText(srt)).toBe("First line.\nSecond line of the same cue.\n\nNext cue.");
  });

  it("degrades to raw text for non-subtitle content", () => {
    expect(subtitlesToText("just words\nno cues")).toBe("just words\nno cues");
  });

  it("returns empty for empty input", () => {
    expect(subtitlesToText("")).toBe("");
  });
});
