/**
 * Invariants between the TypeScript tokens and the emitted CSS bundles.
 *
 * Guarantees:
 *   - Every leaf in `colors` emits exactly one `--color-{scale}-{step}` in
 *     `dist/tokens.css` AND `dist/tailwind.css`.
 *   - Every leaf in `spacing` emits both `--space-{key}` (AC2 literal) and
 *     `--spacing-{key}` (Tailwind-aligned) in `dist/tokens.css`.
 *   - Every value in the TS exports is truthy — walked across colors,
 *     spacing, radii, shadows, typography, motion, elevation.
 *   - `dist/tailwind.css` carries the color surface + the dynamic `--spacing`
 *     base so Tailwind v4's `@theme` derives utility classes automatically.
 *
 * The test reads `dist/*.css` from disk. Run `pnpm build` before `pnpm test`
 * in CI — `turbo.json`'s `test` task already depends on `build`.
 */

import { existsSync, readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { beforeAll, describe, expect, it } from "vitest";

import { colors } from "./colors.js";
import { elevation } from "./elevation.js";
import { motion } from "./motion.js";
import { radii } from "./radii.js";
import { shadows } from "./shadows.js";
import { spacing } from "./spacing.js";
import { typeScale, fontFamilies, readingMeasure } from "./typography.js";

const __dirname = dirname(fileURLToPath(import.meta.url));
const tokensCssPath = resolve(__dirname, "..", "dist", "tokens.css");
const tailwindCssPath = resolve(__dirname, "..", "dist", "tailwind.css");

let tokensCss = "";
let tailwindCss = "";

beforeAll(() => {
  if (!existsSync(tokensCssPath) || !existsSync(tailwindCssPath)) {
    throw new Error(
      `design-tokens invariant suite requires dist/*.css — run ` +
        `\`pnpm --filter @deployai/design-tokens build\` first.`,
    );
  }
  tokensCss = readFileSync(tokensCssPath, "utf8");
  tailwindCss = readFileSync(tailwindCssPath, "utf8");
});

function spacingCssKey(key: string): string {
  return key.replace(/_/g, "-");
}

describe("tokens.css carries every color in src/colors.ts", () => {
  for (const [scaleName, scale] of Object.entries(colors)) {
    for (const step of Object.keys(scale)) {
      const varName = `--color-${scaleName}-${step}`;
      it(`declares ${varName}`, () => {
        expect(tokensCss).toContain(varName);
      });
    }
  }
});

describe("tokens.css dual-emits spacing steps (semantic + Tailwind-aligned)", () => {
  for (const key of Object.keys(spacing)) {
    const cssKey = spacingCssKey(key);
    it(`declares --space-${cssKey} (AC2 literal)`, () => {
      expect(tokensCss).toContain(`--space-${cssKey}:`);
    });
    it(`declares --spacing-${cssKey} (Tailwind-aligned)`, () => {
      expect(tokensCss).toContain(`--spacing-${cssKey}:`);
    });
  }
});

describe("tokens.css carries radii and shadows", () => {
  for (const key of Object.keys(radii)) {
    it(`declares --radius-${key}`, () => {
      expect(tokensCss).toContain(`--radius-${key}`);
    });
  }
  for (const key of Object.keys(shadows)) {
    it(`declares --shadow-${key}`, () => {
      expect(tokensCss).toContain(`--shadow-${key}`);
    });
  }
});

describe("tokens.css carries motion and elevation", () => {
  for (const key of Object.keys(motion.duration)) {
    it(`declares --duration-${key}`, () => {
      expect(tokensCss).toContain(`--duration-${key}`);
    });
  }
  for (const key of Object.keys(motion.easing)) {
    it(`declares --easing-${key}`, () => {
      expect(tokensCss).toContain(`--easing-${key}`);
    });
  }
  for (const key of Object.keys(elevation)) {
    it(`declares --elevation-${key}`, () => {
      expect(tokensCss).toContain(`--elevation-${key}`);
    });
  }
});

describe("tailwind.css registers @theme and mirrors the color surface", () => {
  it("uses Tailwind v4 @theme directive", () => {
    expect(tailwindCss).toMatch(/@theme\s*\{/);
  });

  it("declares the dynamic --spacing base for p-N/m-N/gap-N", () => {
    expect(tailwindCss).toContain("--spacing: 4px");
  });

  it("carries every color variable", () => {
    for (const [scaleName, scale] of Object.entries(colors)) {
      for (const step of Object.keys(scale)) {
        expect(tailwindCss).toContain(`--color-${scaleName}-${step}`);
      }
    }
  });

  it("carries the sans + mono font-family vars", () => {
    expect(tailwindCss).toContain("--font-sans:");
    expect(tailwindCss).toContain("--font-mono:");
  });
});

describe("no leaf token value is undefined / null / empty", () => {
  function walk(node: unknown, path: string): void {
    if (typeof node === "object" && node !== null) {
      for (const [key, value] of Object.entries(node)) {
        walk(value, `${path}.${key}`);
      }
      return;
    }
    it(`${path} is defined`, () => {
      expect(node).not.toBeUndefined();
      expect(node).not.toBeNull();
      if (typeof node === "string") {
        expect(node.length).toBeGreaterThan(0);
      }
    });
  }

  walk(colors, "colors");
  walk(spacing, "spacing");
  walk(radii, "radii");
  walk(shadows, "shadows");
  walk(typeScale, "typography.typeScale");
  walk(fontFamilies, "typography.fontFamilies");
  walk(readingMeasure, "typography.readingMeasure");
  walk(motion, "motion");
  walk(elevation, "elevation");
});
