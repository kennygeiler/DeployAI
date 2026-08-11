/**
 * Border-radius tokens — Beautiful UI geometry.
 *
 * Chips 6px, controls 8px, cards 10px, pills full — buttons in this system
 * are pill-shaped (`full`) and cards sit at `card` (10px).
 */
export const radii = {
  none: "0",
  sm: "4px",
  /** Inline chips, tags, source chips. */
  chip: "6px",
  md: "8px",
  /** Buttons-as-rects, inputs, small controls. */
  control: "8px",
  /** Cards, panels, wells. */
  card: "10px",
  lg: "12px",
  xl: "16px",
  /** Pill buttons. */
  full: "9999px",
} as const;

export type Radii = typeof radii;
export type RadiusKey = keyof Radii;
