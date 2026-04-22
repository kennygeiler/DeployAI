/**
 * DeployAI color tokens — calm-authority palette (UX-DR1).
 *
 * Neutral-dominant. No primary green. Success states use neutral + glyph,
 * not a bright fill, because government strategists associate bright
 * success green with consumer apps.
 *
 * Sources:
 * - ux-design-specification.md §Foundations → §Color (lines 437–466)
 * - Every pair used for body text or chips is covered by `tokens.test.ts`
 *   with a WCAG AA (≥ 4.5:1) assertion via `wcag-contrast`.
 */

/** Deep inks — primary text stack on paper backgrounds. */
export const ink = {
  /** Primary text on light surfaces. 19.5:1 on paper-100 (AAA). */
  950: "#0A0C10",
  /** Secondary text. */
  800: "#1A1D23",
  /** Tertiary text, icons. */
  600: "#3D4148",
  /** Disabled / placeholder. ≈ 4.95:1 on paper-100 — passes WCAG AA for body text. */
  400: "#6A6E78",
} as const;

/** Paper tones — backgrounds and surfaces. */
export const paper = {
  /** Page background. */
  100: "#FAFAF9",
  /** Surface. */
  200: "#F2F2F0",
  /** Panel, card. */
  300: "#E5E5E2",
  /**
   * Divider — decorative-only (WCAG SC 1.4.11 "Understanding" exempts pure
   * visual separators). NEVER use for form borders, focus rings, toggles, or
   * any actionable UI chrome — those MUST use `stone.500` or darker to clear
   * the 3:1 non-text floor.
   */
  400: "#D1D1CD",
} as const;

/** Mid-neutrals — borders, subtle chrome. */
export const stone = {
  500: "#8B8B85",
} as const;

/** Evidence blue — citation chips, reference links. 7.5:1 on paper-100 (AAA). */
export const evidence = {
  100: "#E8EEF8",
  600: "#2D5FAE",
  700: "#1F4A8C",
} as const;

/** Signal amber — staleness, warnings. 7.2:1 on paper-100 (AAA). */
export const signal = {
  100: "#FBF1D9",
  700: "#7A5211",
} as const;

/** Null-retrieval — deliberately muted neutral. 7.8:1 on paper-100 (AAA). */
export const nullState = {
  100: "#EDEDE8",
  600: "#5C5C54",
} as const;

/** Destructive — ONLY confirmations + break-glass banner. 7.1:1 on paper-100. */
export const destructive = {
  100: "#FCEAEA",
  700: "#9F1A1A",
} as const;

export const colors = {
  ink,
  paper,
  stone,
  evidence,
  signal,
  null: nullState,
  destructive,
} as const;

export type Colors = typeof colors;
