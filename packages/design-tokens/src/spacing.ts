/**
 * Spacing tokens — 4 px base scale (UX-DR1).
 *
 * Keys use underscore-separated decimals (`0_5`, `1_5`) so TypeScript
 * consumers can use bracket access without quoting, and CSS custom
 * properties derive their names by replacing `_` with `-` (e.g. `0_5` →
 * `--space-0-5`).
 */
export const spacing = {
  "0": "0",
  "0_5": "2px",
  "1": "4px",
  "1_5": "6px",
  "2": "8px",
  "3": "12px",
  "4": "16px",
  "6": "24px",
  "8": "32px",
  "12": "48px",
  "16": "64px",
  "24": "96px",
} as const;

export type Spacing = typeof spacing;
export type SpacingKey = keyof Spacing;
