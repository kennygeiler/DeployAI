import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { describe, expect, it } from "vitest";

import { TOUR_STEPS } from "@/lib/tour/steps";

/**
 * K7 — the slip act serves copies of `demo/artifacts/*` from
 * `apps/web/public/demo/` (the tour's prefill buttons fetch them; the .vtt is
 * a download link). The repo copies are the source of truth for presenters —
 * this test fails loudly if the two ever drift.
 */

const PUBLIC_DIR = resolve(__dirname, "../../../public/demo");
const ARTIFACTS_DIR = resolve(__dirname, "../../../../../demo/artifacts");

const SERVED = ["kickoff-transcript.txt", "slip-email.txt", "acme-standup.vtt"] as const;

describe("public demo artifacts", () => {
  it.each(SERVED)("%s matches demo/artifacts", (name) => {
    const served = readFileSync(resolve(PUBLIC_DIR, name), "utf8");
    const source = readFileSync(resolve(ARTIFACTS_DIR, name), "utf8");
    expect(served).toBe(source);
  });

  it("every tour capture-prefill / download URL points at a served artifact", () => {
    const servedUrls = new Set(SERVED.map((n) => `/demo/${n}`));
    for (const step of TOUR_STEPS) {
      if (step.capturePrefill) {
        expect(servedUrls.has(step.capturePrefill.url), step.id).toBe(true);
      }
      if (step.download) {
        expect(servedUrls.has(step.download.href), step.id).toBe(true);
      }
    }
  });

  it("the slip email buries the date change mid-thread (Oct 3 → Oct 17)", () => {
    const slip = readFileSync(resolve(ARTIFACTS_DIR, "slip-email.txt"), "utf8");
    expect(slip).toContain("October 17");
    expect(slip).toContain("October 3");
    const vtt = readFileSync(resolve(ARTIFACTS_DIR, "acme-standup.vtt"), "utf8");
    expect(vtt.startsWith("WEBVTT")).toBe(true);
    expect(vtt).toContain("safety certification");
  });
});
