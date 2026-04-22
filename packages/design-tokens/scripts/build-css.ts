/**
 * Emit `dist/tokens.css` (raw CSS custom properties — dual-emit semantic +
 * Tailwind-aligned names, so direct consumers can pick either) and
 * `dist/tailwind.css` (Tailwind v4 `@theme` preset using Tailwind's naming
 * conventions so `bg-ink-950`, `text-display`, `font-sans`, `rounded-md`,
 * `shadow-sm`, `p-4` all derive automatically).
 *
 * Run after `tsc` by `pnpm build`. Imports from `../src/*` via `tsx`, so
 * there is no circular dependency on the compiled JS.
 *
 * Output is deterministic — no timestamps, no machine paths, no user data.
 *
 * Tailwind v4 `@theme` naming reference:
 *   --color-*              → bg-*, text-*, border-*, ring-*
 *   --font-*               → font-* (family)
 *   --text-*               → text-* (size), pairs with --text-*--line-height
 *   --spacing              → single base for dynamic p-N, m-N, gap-N
 *   --spacing-*            → static utility overrides
 *   --radius-*             → rounded-*
 *   --shadow-*             → shadow-*
 *   --font-weight-*        → font-* (weight)
 */

import { mkdir, writeFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { colors } from "../src/colors.js";
import { elevation } from "../src/elevation.js";
import { motion } from "../src/motion.js";
import { radii } from "../src/radii.js";
import { shadows } from "../src/shadows.js";
import { spacing } from "../src/spacing.js";
import { fontFamilies, readingMeasure, typeScale } from "../src/typography.js";

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);
const distDir = resolve(__dirname, "..", "dist");

/**
 * Reject any token value that would break the enclosing `:root {}` / `@theme {}`
 * block if interpolated as-is (a stray `;`, `}`, newline, or block comment).
 * Throws with the token path so the offending leaf is trivial to locate.
 */
function assertSafeValue(path: string, value: unknown): void {
  if (typeof value !== "string" && typeof value !== "number") {
    throw new Error(`design-tokens build: non-string/number token at '${path}': ${String(value)}`);
  }
  const str = String(value);
  if (/[;}\n\r]/.test(str) || str.includes("/*") || str.includes("*/")) {
    throw new Error(
      `design-tokens build: token '${path}' contains a CSS-unsafe character: ${JSON.stringify(str)}`,
    );
  }
}

function spacingKey(key: string): string {
  return key.replace(/_/g, "-");
}

function colorVars(): string[] {
  const lines: string[] = [];
  for (const [scaleName, scale] of Object.entries(colors)) {
    for (const [step, value] of Object.entries(scale)) {
      assertSafeValue(`colors.${scaleName}.${step}`, value);
      lines.push(`  --color-${scaleName}-${step}: ${value};`);
    }
  }
  return lines;
}

/** Tailwind v4 spacing: emit just the dynamic base so `p-N`, `m-N`, `gap-N` all derive. */
function spacingVarsTailwind(): string[] {
  return [`  --spacing: 4px;`];
}

/**
 * tokens.css spacing: dual-emit.
 *   --space-{key}     — AC2 literal (semantic naming)
 *   --spacing-{key}   — Tailwind-aligned static override name
 *   --spacing         — Tailwind dynamic base (also usable outside Tailwind)
 * Any direct CSS consumer can pick whichever convention matches their codebase.
 */
function spacingVarsSemantic(): string[] {
  const lines: string[] = [`  --spacing: 4px;`];
  for (const [key, value] of Object.entries(spacing)) {
    assertSafeValue(`spacing.${key}`, value);
    const cssKey = spacingKey(key);
    lines.push(`  --space-${cssKey}: ${value};`);
    lines.push(`  --spacing-${cssKey}: ${value};`);
  }
  return lines;
}

function radiusVars(): string[] {
  return Object.entries(radii).map(([key, value]) => {
    assertSafeValue(`radii.${key}`, value);
    return `  --radius-${key}: ${value};`;
  });
}

function shadowVars(): string[] {
  return Object.entries(shadows).map(([key, value]) => {
    assertSafeValue(`shadows.${key}`, value);
    return `  --shadow-${key}: ${value};`;
  });
}

function elevationVars(): string[] {
  return Object.entries(elevation).map(([key, value]) => {
    assertSafeValue(`elevation.${key}`, value);
    return `  --elevation-${key}: ${String(value)};`;
  });
}

/** Tailwind v4-idiomatic font and text tokens (see header comment). */
function typographyVarsTailwind(): string[] {
  const lines: string[] = [];
  assertSafeValue(`typography.fontFamilies.sans`, fontFamilies.sans);
  assertSafeValue(`typography.fontFamilies.mono`, fontFamilies.mono);
  lines.push(`  --font-sans: ${fontFamilies.sans};`);
  lines.push(`  --font-mono: ${fontFamilies.mono};`);
  for (const [step, scale] of Object.entries(typeScale)) {
    assertSafeValue(`typography.scale.${step}.size`, scale.size);
    assertSafeValue(`typography.scale.${step}.lineHeight`, scale.lineHeight);
    assertSafeValue(`typography.scale.${step}.letterSpacing`, scale.letterSpacing);
    assertSafeValue(`typography.scale.${step}.weight`, scale.weight);
    lines.push(`  --text-${step}: ${scale.size};`);
    lines.push(`  --text-${step}--line-height: ${scale.lineHeight};`);
    lines.push(`  --text-${step}--letter-spacing: ${scale.letterSpacing};`);
    lines.push(`  --text-${step}--font-weight: ${String(scale.weight)};`);
  }
  return lines;
}

/** Semantic typography vars for non-Tailwind consumers (tokens.css only). */
function typographyVarsSemantic(): string[] {
  const lines: string[] = [];
  lines.push(`  --font-family-sans: ${fontFamilies.sans};`);
  lines.push(`  --font-family-mono: ${fontFamilies.mono};`);
  lines.push(`  --font-sans: ${fontFamilies.sans};`);
  lines.push(`  --font-mono: ${fontFamilies.mono};`);
  for (const [step, scale] of Object.entries(typeScale)) {
    lines.push(`  --text-${step}: ${scale.size};`);
    lines.push(`  --text-${step}-size: ${scale.size};`);
    lines.push(`  --text-${step}-line-height: ${scale.lineHeight};`);
    lines.push(`  --text-${step}-letter-spacing: ${scale.letterSpacing};`);
    lines.push(`  --text-${step}-weight: ${String(scale.weight)};`);
  }
  assertSafeValue(`typography.readingMeasure.min`, readingMeasure.min);
  assertSafeValue(`typography.readingMeasure.max`, readingMeasure.max);
  lines.push(`  --reading-measure-min: ${readingMeasure.min};`);
  lines.push(`  --reading-measure-max: ${readingMeasure.max};`);
  return lines;
}

function motionVars(): string[] {
  const lines: string[] = [];
  for (const [key, value] of Object.entries(motion.duration)) {
    assertSafeValue(`motion.duration.${key}`, value);
    lines.push(`  --duration-${key}: ${value};`);
  }
  for (const [key, value] of Object.entries(motion.easing)) {
    assertSafeValue(`motion.easing.${key}`, value);
    lines.push(`  --easing-${key}: ${value};`);
  }
  return lines;
}

const HEADER =
  "/* @deployai/design-tokens — generated by scripts/build-css.ts. DO NOT EDIT. */\n" +
  "/* Source of truth: packages/design-tokens/src/*. Satisfies UX-DR1, UX-DR2. */\n";

function renderSections(sections: Array<[string, string[]]>): string {
  return sections
    .map(([name, lines]) => `  /* --- ${name} --- */\n${lines.join("\n")}`)
    .join("\n\n");
}

function emitTokensCss(): string {
  const body = renderSections([
    ["Color", colorVars()],
    ["Spacing (4px base — dual-emit `--space-*` + `--spacing-*`)", spacingVarsSemantic()],
    ["Radii", radiusVars()],
    ["Shadows", shadowVars()],
    ["Elevation (z-index)", elevationVars()],
    ["Typography", typographyVarsSemantic()],
    ["Motion", motionVars()],
  ]);

  return `${HEADER}\n:root {\n${body}\n}\n`;
}

function emitTailwindCss(): string {
  const body = renderSections([
    ["Color", colorVars()],
    ["Spacing (Tailwind v4 dynamic base)", spacingVarsTailwind()],
    ["Radii", radiusVars()],
    ["Shadows", shadowVars()],
    ["Typography", typographyVarsTailwind()],
  ]);

  return `${HEADER}\n@theme {\n${body}\n}\n`;
}

async function main(): Promise<void> {
  await mkdir(distDir, { recursive: true });
  await writeFile(resolve(distDir, "tokens.css"), emitTokensCss(), "utf8");
  await writeFile(resolve(distDir, "tailwind.css"), emitTailwindCss(), "utf8");
}

main().catch((error: unknown) => {
  console.error(error);
  process.exit(1);
});
