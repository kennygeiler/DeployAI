/**
 * Shadow tokens — Beautiful UI elevation ladder.
 *
 * Every level is "hairline-ringed": the first layer is always a
 * `0 0 0 1px var(--line[-strong])` ring so elevated surfaces read as crisp
 * cards rather than blurry blobs. The ring references the runtime `--line`
 * vars, so shadows re-theme automatically in dark mode; the soft layers get
 * explicit dark overrides (`shadowsDark`) emitted under `.dark`.
 *
 * Ladder (5 levels + inset):
 *   hairline    — flat bordered surface (chips, wells)
 *   btn         — buttons, small controls (stronger ring + 1px drop)
 *   card        — cards, panels
 *   raised      — hover states, popped rows
 *   overlay     — popovers, dialogs, menus
 *   inset-field — text fields / composer wells
 */

export const shadows = {
  none: "none",
  hairline: "0 0 0 1px var(--line)",
  btn: "0 0 0 1px var(--line-strong), 0 1px 2px rgba(16, 24, 40, 0.05)",
  card: "0 0 0 1px var(--line), 0 1px 2px rgba(16, 24, 40, 0.04), 0 2px 6px rgba(16, 24, 40, 0.03)",
  raised: "0 0 0 1px var(--line), 0 2px 10px rgba(0, 0, 0, 0.04)",
  overlay: "0 0 0 1px var(--line), 0 8px 28px rgba(0, 0, 0, 0.07)",
  "inset-field": "inset 0 1px 2px rgba(0, 0, 0, 0.12)",
  /* Legacy aliases — existing `shadow-sm|md|lg` usages map onto the ladder. */
  sm: "0 0 0 1px var(--line), 0 1px 2px rgba(16, 24, 40, 0.04)",
  md: "0 0 0 1px var(--line), 0 1px 2px rgba(16, 24, 40, 0.04), 0 2px 6px rgba(16, 24, 40, 0.03)",
  lg: "0 0 0 1px var(--line), 0 8px 28px rgba(0, 0, 0, 0.07)",
  /** Focus ring (for elements that can't use `outline`). */
  focus: "0 0 0 2px var(--surface), 0 0 0 4px var(--accent)",
} as const;

/** Dark-mode soft-layer overrides (rings still follow `--line` vars). */
export const shadowsDark = {
  btn: "0 0 0 1px var(--line-strong), 0 1px 2px rgba(0, 0, 0, 0.30)",
  card: "0 0 0 1px var(--line), 0 1px 2px rgba(0, 0, 0, 0.20), 0 2px 6px rgba(0, 0, 0, 0.20)",
  raised: "0 0 0 1px var(--line), 0 2px 10px rgba(0, 0, 0, 0.22)",
  overlay: "0 0 0 1px var(--line-strong), 0 8px 28px rgba(0, 0, 0, 0.34)",
  "inset-field": "inset 0 1px 2px rgba(0, 0, 0, 0.40)",
  sm: "0 0 0 1px var(--line), 0 1px 2px rgba(0, 0, 0, 0.20)",
  md: "0 0 0 1px var(--line), 0 1px 2px rgba(0, 0, 0, 0.20), 0 2px 6px rgba(0, 0, 0, 0.20)",
  lg: "0 0 0 1px var(--line-strong), 0 8px 28px rgba(0, 0, 0, 0.34)",
} as const;

export type Shadows = typeof shadows;
export type ShadowKey = keyof Shadows;
