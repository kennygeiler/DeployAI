/**
 * Epic 9 Story 9.2 — enforce Oracle’s three-item surface budget (FR22/FR36).
 */
export function splitPrimaryAndRankedOut<T>(
  items: readonly T[],
  maxPrimary = 3,
): {
  primary: readonly T[];
  rankedOut: readonly T[];
} {
  const n = Math.max(0, Math.min(100, Math.floor(maxPrimary)));
  return {
    primary: items.slice(0, n),
    rankedOut: items.slice(n),
  };
}
