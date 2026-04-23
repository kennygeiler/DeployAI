/**
 * Stand-in for a future `CitationChip` — only `var(--*)` references, no raw hex.
 */

export type CitationChipStyle = {
  background: string;
  color: string;
  borderRadius: string;
  fontFamily: string;
};

export function citationChipStyle(): CitationChipStyle {
  return {
    background: "var(--color-paper-100)",
    color: "var(--color-ink-950)",
    borderRadius: "var(--radius-md)",
    fontFamily: "var(--font-sans)",
  };
}

export function assertOnlyDesignTokens(style: CitationChipStyle) {
  for (const v of Object.values(style)) {
    if (!v.startsWith("var(--")) {
      throw new Error(`Non-token style (expected CSS var): ${v}`);
    }
  }
}
