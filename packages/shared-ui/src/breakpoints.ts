/**
 * Canonical layout breakpoints (UX-DR37 / UX-DR38), aligned with Tailwind v4 defaults.
 * Use for documentation and for hooks like `useMobileReadOnlyGate` (default 768 = `md:`).
 */
export const BREAKPOINT_PX = {
  sm: 640,
  md: 768,
  lg: 1024,
  xl: 1280,
  "2xl": 1536,
} as const;

/** Viewports at or below this width match Tailwind’s default (mobile) range < `md:`. */
export const MOBILE_READ_ONLY_PX: number = BREAKPOINT_PX.md;
