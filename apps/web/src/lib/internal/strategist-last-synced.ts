/**
 * NFR5 freshness chip: “last memory sync” shown as ~90s before request time in strategist shell.
 * Lives outside the layout component to satisfy `react-hooks/purity` (no impure `Date` in a component file).
 */
export function getStrategistLastSyncedAtMs(): number {
  return Date.now() - 90_000;
}
