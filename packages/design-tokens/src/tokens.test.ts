/**
 * WCAG AA (and AAA where the spec demands) contrast assertions for every
 * token pair the design system uses for body text, chips, card surfaces,
 * and non-text UI components — updated for the Beautiful UI palette.
 *
 * WCAG 2.1 SC 1.4.3 (Contrast Minimum):
 *   - Body text: ≥ 4.5:1
 *   - Large text (≥ 18pt / 14pt bold): ≥ 3:1
 *   - UI components & graphics (SC 1.4.11): ≥ 3:1
 *
 * WCAG 2.1 SC 1.4.6 (Contrast Enhanced / AAA):
 *   - Body text: ≥ 7:1
 *
 * Beautiful UI deviations enforced here:
 *   - `ink-3` (light #9a9da3) fails AA on white BY DESIGN and is reserved
 *     for decorative/disabled glyphs only. It is deliberately EXCLUDED from
 *     the text-pair tables; placeholder/disabled TEXT uses `ink-400`, which
 *     IS asserted at AA below.
 *   - Raw `accent`/`green`/`orange`/`red` hues are fills/graphics (asserted
 *     at the 3:1 non-text floor where interactive); their `*-ink` companions
 *     carry text duty and are asserted at AA on white AND on their tints.
 *   - The AAA CitationChip target moved from `evidence-700` to
 *     `evidence-800`: Beautiful UI's accent-as-text sits at ~5.8:1 (AA),
 *     so 700 is the AA link/citation text tone and 800 the AAA option.
 */

import { describe, expect, it } from "vitest";
import { hex } from "wcag-contrast";

import {
  destructive,
  evidence,
  ink,
  nullState,
  paper,
  signal,
  stone,
  themeDark,
  themeLight,
} from "./colors.js";

const AA_BODY = 4.5;
const AA_LARGE_OR_UI = 3.0;
const AAA_BODY = 7.0;

type Pair = {
  readonly name: string;
  readonly fg: string;
  readonly bg: string;
};

function ratio(fg: string, bg: string): number {
  return hex(fg, bg);
}

describe("body-text pairs must meet WCAG AA (≥ 4.5:1) on page (paper-100)", () => {
  const pairs: Pair[] = [
    { name: "ink-950 / paper-100", fg: ink[950], bg: paper[100] },
    { name: "ink-800 / paper-100", fg: ink[800], bg: paper[100] },
    { name: "ink-700 / paper-100", fg: ink[700], bg: paper[100] },
    { name: "ink-600 / paper-100", fg: ink[600], bg: paper[100] },
    { name: "ink-500 (ink-2) / paper-100", fg: ink[500], bg: paper[100] },
    { name: "ink-400 / paper-100 (disabled + placeholder)", fg: ink[400], bg: paper[100] },
    { name: "semantic ink / page", fg: themeLight.ink, bg: themeLight.page },
    { name: "semantic ink-2 / page", fg: themeLight["ink-2"], bg: themeLight.page },
    { name: "accent-ink / page (links)", fg: themeLight["accent-ink"], bg: themeLight.page },
    { name: "evidence-700 / paper-100", fg: evidence[700], bg: paper[100] },
    { name: "signal-700 / paper-100", fg: signal[700], bg: paper[100] },
    { name: "null-600 / paper-100", fg: nullState[600], bg: paper[100] },
    { name: "destructive-700 / paper-100", fg: destructive[700], bg: paper[100] },
    { name: "green-ink / page", fg: themeLight["green-ink"], bg: themeLight.page },
    { name: "orange-ink / page", fg: themeLight["orange-ink"], bg: themeLight.page },
    { name: "red-ink / page", fg: themeLight["red-ink"], bg: themeLight.page },
  ];

  it.each(pairs)("$name ≥ 4.5:1", ({ fg, bg }) => {
    expect(ratio(fg, bg)).toBeGreaterThanOrEqual(AA_BODY);
  });
});

describe("surface-ladder body-text pairs must meet WCAG AA on every well", () => {
  const pairs: Pair[] = [
    { name: "ink-950 / surface (paper-50)", fg: ink[950], bg: paper[50] },
    { name: "ink-2 / surface", fg: themeLight["ink-2"], bg: themeLight.surface },
    { name: "ink-950 / canvas (paper-200)", fg: ink[950], bg: paper[200] },
    { name: "ink-800 / paper-200", fg: ink[800], bg: paper[200] },
    { name: "ink-600 / paper-200", fg: ink[600], bg: paper[200] },
    { name: "ink-2 / inset", fg: themeLight["ink-2"], bg: themeLight.inset },
    { name: "ink-2 / hover", fg: themeLight["ink-2"], bg: themeLight.hover },
    { name: "ink-950 / hover-2 (paper-300)", fg: ink[950], bg: paper[300] },
    { name: "ink-800 / paper-300", fg: ink[800], bg: paper[300] },
    { name: "ink-600 / hover-2", fg: ink[600], bg: themeLight["hover-2"] },
    { name: "ink-2 / field", fg: themeLight["ink-2"], bg: themeLight.field },
  ];

  it.each(pairs)("$name ≥ 4.5:1", ({ fg, bg }) => {
    expect(ratio(fg, bg)).toBeGreaterThanOrEqual(AA_BODY);
  });
});

describe("chip pairs (colored label on tinted fill) must meet WCAG AA", () => {
  const pairs: Pair[] = [
    { name: "evidence-700 / evidence-100", fg: evidence[700], bg: evidence[100] },
    { name: "accent-ink strong / accent-tint", fg: evidence[700], bg: themeLight["accent-tint"] },
    { name: "signal-700 / signal-100", fg: signal[700], bg: signal[100] },
    { name: "null-600 / null-100", fg: nullState[600], bg: nullState[100] },
    { name: "destructive-700 / destructive-100", fg: destructive[700], bg: destructive[100] },
    { name: "green-ink / green-tint", fg: themeLight["green-ink"], bg: themeLight["green-tint"] },
    {
      name: "orange-ink / orange-tint",
      fg: themeLight["orange-ink"],
      bg: themeLight["orange-tint"],
    },
    { name: "red-ink / red-tint", fg: themeLight["red-ink"], bg: themeLight["red-tint"] },
  ];

  it.each(pairs)("$name ≥ 4.5:1", ({ fg, bg }) => {
    expect(ratio(fg, bg)).toBeGreaterThanOrEqual(AA_BODY);
  });
});

describe("inverted chip pairs (paper label on solid fill) must meet WCAG AA", () => {
  const pairs: Pair[] = [
    { name: "paper-100 / evidence-700", fg: paper[100], bg: evidence[700] },
    { name: "paper-100 / signal-700", fg: paper[100], bg: signal[700] },
    { name: "paper-100 / null-600", fg: paper[100], bg: nullState[600] },
    { name: "paper-100 / destructive-700", fg: paper[100], bg: destructive[700] },
    { name: "white / green-ink", fg: themeLight.surface, bg: themeLight["green-ink"] },
    { name: "tooltip-fg / tooltip-bg", fg: themeLight["tooltip-fg"], bg: themeLight["tooltip-bg"] },
  ];

  it.each(pairs)("$name ≥ 4.5:1", ({ fg, bg }) => {
    expect(ratio(fg, bg)).toBeGreaterThanOrEqual(AA_BODY);
  });
});

describe("AAA targets (CitationChip, primary text) must meet ≥ 7:1", () => {
  it("ink-950 / paper-100 reaches AAA", () => {
    expect(ratio(ink[950], paper[100])).toBeGreaterThanOrEqual(AAA_BODY);
  });

  it("evidence-800 / paper-100 reaches AAA (CitationChip AAA target)", () => {
    expect(ratio(evidence[800], paper[100])).toBeGreaterThanOrEqual(AAA_BODY);
  });
});

describe("non-text UI components must meet WCAG SC 1.4.11 (≥ 3:1)", () => {
  // Note: paper-400 / line / line-strong are decorative-only hairlines (pure
  // visual separators, WCAG-exempt per SC 1.4.11 "Understanding"). Any
  // actionable UI chrome (form borders, focus rings, toggles) MUST use
  // stone-500 or darker — this suite enforces that contract. The raw accent
  // hue is a graphics/fill color and must clear the 3:1 floor.
  const pairs: Pair[] = [
    { name: "stone-500 / paper-100 (form-field border)", fg: stone[500], bg: paper[100] },
    { name: "accent (evidence-600) / paper-100 (fills)", fg: evidence[600], bg: paper[100] },
    { name: "accent / surface", fg: themeLight.accent, bg: themeLight.surface },
  ];

  it.each(pairs)("$name ≥ 3:1", ({ fg, bg }) => {
    expect(ratio(fg, bg)).toBeGreaterThanOrEqual(AA_LARGE_OR_UI);
  });
});

describe("dark theme solid text pairs must meet WCAG AA", () => {
  // Alpha tints are excluded (composited color depends on the surface
  // beneath); every solid dark-theme text pair is asserted here.
  const pairs: Pair[] = [
    { name: "dark ink / page", fg: themeDark.ink, bg: themeDark.page },
    { name: "dark ink / surface", fg: themeDark.ink, bg: themeDark.surface },
    { name: "dark ink-2 / surface", fg: themeDark["ink-2"], bg: themeDark.surface },
    { name: "dark ink-2 / hover-2", fg: themeDark["ink-2"], bg: themeDark["hover-2"] },
    { name: "dark accent-ink / surface", fg: themeDark["accent-ink"], bg: themeDark.surface },
    { name: "dark green-ink / surface", fg: themeDark["green-ink"], bg: themeDark.surface },
    { name: "dark orange-ink / surface", fg: themeDark["orange-ink"], bg: themeDark.surface },
    { name: "dark red-ink / surface", fg: themeDark["red-ink"], bg: themeDark.surface },
    {
      name: "dark tooltip-fg / tooltip-bg",
      fg: themeDark["tooltip-fg"],
      bg: themeDark["tooltip-bg"],
    },
  ];

  it.each(pairs)("$name ≥ 4.5:1", ({ fg, bg }) => {
    expect(ratio(fg, bg)).toBeGreaterThanOrEqual(AA_BODY);
  });
});
