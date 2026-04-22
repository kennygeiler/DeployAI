/**
 * Motion tokens — minimal set for V1.
 *
 * Per ux-design-specification.md §Accessibility (line 970), `prefers-reduced-motion`
 * disables non-essential transitions and reduces essential expand/collapse to a
 * 50 ms cross-fade. Consumers are expected to honor the `reducedMotion` step.
 *
 * Full motion tokens (ease curves, durations by interaction class) arrive in Epic 7.
 */
export const motion = {
  duration: {
    instant: "0ms",
    "reduced-motion": "50ms",
    fast: "120ms",
    base: "200ms",
  },
  easing: {
    standard: "cubic-bezier(0.2, 0, 0, 1)",
    out: "cubic-bezier(0, 0, 0.2, 1)",
  },
} as const;

export type Motion = typeof motion;
