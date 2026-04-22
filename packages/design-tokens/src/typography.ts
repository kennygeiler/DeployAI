/**
 * Typography tokens — Inter for UI + IBM Plex Mono for citations/IDs (UX-DR2).
 *
 * Exact scale per ux-design-specification.md §Typography. All sizes are in
 * rem so they respect user-agent font-size preferences; line-heights are
 * unitless ratios for the same reason.
 */

export const fontFamilies = {
  /** Primary sans stack. `--font-inter` is the next/font CSS variable. */
  sans: "var(--font-inter), 'Inter', system-ui, -apple-system, 'Segoe UI', sans-serif",
  /** Mono stack for citations, IDs, code. */
  mono: "var(--font-mono), 'IBM Plex Mono', 'SFMono-Regular', Consolas, 'Liberation Mono', monospace",
} as const;

/**
 * Type ramp — `{size, lineHeight, letterSpacing, weight}` per scale step.
 * `size` is in rem (1 rem = 16 px at default root).
 */
export const typeScale = {
  display: {
    size: "2rem",
    lineHeight: "1.25",
    letterSpacing: "-0.01em",
    weight: 600,
  },
  heading: {
    size: "1.25rem",
    lineHeight: "1.4",
    letterSpacing: "-0.005em",
    weight: 600,
  },
  body: {
    size: "1rem",
    lineHeight: "1.5",
    letterSpacing: "0",
    weight: 400,
  },
  small: {
    size: "0.875rem",
    lineHeight: "1.43",
    letterSpacing: "0",
    weight: 400,
  },
  micro: {
    size: "0.75rem",
    lineHeight: "1.33",
    letterSpacing: "0.01em",
    weight: 500,
  },
} as const;

/** Reading measure for long-form prose (evidence panels, override rationale). */
export const readingMeasure = {
  min: "60ch",
  max: "72ch",
} as const;

export const typography = {
  fontFamilies,
  scale: typeScale,
  readingMeasure,
} as const;

export type Typography = typeof typography;
export type TypeScaleStep = keyof typeof typeScale;
