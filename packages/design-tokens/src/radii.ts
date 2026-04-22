/**
 * Border-radius tokens (UX-DR1).
 * Small, consistent rounding; no playful large radii.
 */
export const radii = {
  none: "0",
  sm: "2px",
  md: "6px",
  lg: "10px",
  full: "9999px",
} as const;

export type Radii = typeof radii;
export type RadiusKey = keyof Radii;
