/**
 * z-index elevation scale (UX-DR1).
 * Deliberately sparse; new layers must be added here rather than inline.
 */
export const elevation = {
  base: 0,
  raised: 1,
  overlay: 10,
  dropdown: 20,
  modal: 100,
  toast: 200,
} as const;

export type Elevation = typeof elevation;
export type ElevationKey = keyof Elevation;
