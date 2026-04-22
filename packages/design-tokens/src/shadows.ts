/**
 * Shadow tokens — calm-authority means very subtle elevation cues (UX-DR1).
 * Shadows are layered rgba() of ink-950 so they stay neutral across themes.
 */
import { evidence, paper } from "./colors.js";

export const shadows = {
  none: "none",
  sm: "0 1px 2px rgba(10, 12, 16, 0.04), 0 1px 1px rgba(10, 12, 16, 0.03)",
  md: "0 2px 4px rgba(10, 12, 16, 0.06), 0 1px 2px rgba(10, 12, 16, 0.04)",
  lg: "0 8px 16px rgba(10, 12, 16, 0.08), 0 2px 4px rgba(10, 12, 16, 0.04)",
  /** Focus-ring shadow (for synthetic rings on elements that can't use `outline`). */
  focus: `0 0 0 2px ${paper[100]}, 0 0 0 4px ${evidence[700]}`,
} as const;

export type Shadows = typeof shadows;
export type ShadowKey = keyof Shadows;
