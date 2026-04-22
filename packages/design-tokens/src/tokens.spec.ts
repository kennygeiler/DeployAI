/**
 * Invariants between the TypeScript tokens and the emitted CSS bundles.
 *
 * Guarantees:
 *   - Every leaf in `colors` emits exactly one `--color-{scale}-{step}` in
 *     `dist/tokens.css`.
 *   - Every leaf in `spacing` emits exactly one `--space-{key}` (with `_`
 *     rewritten to `-`).
 *   - Every value in the TS exports is truthy (catches typos like `undefined`
 *     slipping into a spread).
 *   - `dist/tailwind.css` carries the same color + spacing surface so that
 *     Tailwind v4's `@theme` derives utility classes automatically.
 *
 * The test reads `dist/*.css` from disk. Run `pnpm build` before `pnpm test`
 * in CI — `turbo.json`'s `test` task already depends on `build`.
 */

import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { beforeAll, describe, expect, it } from "vitest";

import { colors } from "./colors.js";
import { radii } from "./radii.js";
import { shadows } from "./shadows.js";
import { spacing } from "./spacing.js";

const __dirname = dirname(fileURLToPath(import.meta.url));
const tokensCssPath = resolve(__dirname, "..", "dist", "tokens.css");
const tailwindCssPath = resolve(__dirname, "..", "dist", "tailwind.css");

let tokensCss = "";
let tailwindCss = "";

beforeAll(() => {
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

describe("tokens.css carries every spacing step in src/spacing.ts", () => {
  for (const key of Object.keys(spacing)) {
    const varName = `--spacing-${spacingCssKey(key)}`;
    it(`declares ${varName}`, () => {
      expect(tokensCss).toContain(varName);
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

describe("tailwind.css registers @theme and mirrors the color + spacing surface", () => {
  it("uses Tailwind v4 @theme directive", () => {
    expect(tailwindCss).toMatch(/@theme\s*\{/);
  });

  it("carries every color variable", () => {
    for (const [scaleName, scale] of Object.entries(colors)) {
      for (const step of Object.keys(scale)) {
        expect(tailwindCss).toContain(`--color-${scaleName}-${step}`);
      }
    }
  });

  it("carries every spacing step", () => {
    for (const key of Object.keys(spacing)) {
      expect(tailwindCss).toContain(`--spacing-${spacingCssKey(key)}`);
    }
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
});
