/**
 * DeployAI color tokens — Beautiful UI design language.
 *
 * Palette extracted from the Beautiful UI reference (beautiful-ui-five.vercel.app):
 *   - Surface ladder: page → canvas → surface → inset → hover → hover-2
 *   - Ink ladder: ink (primary) → ink-2 (secondary) → ink-3 (decorative ONLY)
 *   - Hairlines: line / line-strong
 *   - Accent (blue) + semantic green/orange/red, each with a tint fill
 *   - Dedicated tooltip surface (always dark-on-light-ish inversion)
 *
 * Both light and dark theme values are exported; the dark theme is applied
 * via `.dark` / `[data-theme="dark"]` overrides emitted in `dist/tokens.css`.
 *
 * WCAG notes (all enforced in `tokens.test.ts`):
 *   - Every pair used for body text or chips is asserted at AA (≥ 4.5:1).
 *   - Beautiful UI's `ink-3` (#9a9da3) fails AA on white (≈ 2.7:1). It is
 *     reserved for decorative/disabled glyphs only and is deliberately
 *     excluded from the tested text pairs. Placeholder/disabled TEXT uses
 *     `ink-400`, which is tuned to clear AA.
 *   - Beautiful UI's raw `accent`/`green`/`orange`/`red` fail AA as body
 *     text on white; each gets a tuned `*-ink` companion that passes on
 *     both white and its tint. The raw hue is kept for fills, meters, and
 *     large glyphs (≥ 3:1 where interactive).
 *
 * Legacy scale names (`ink-*`, `paper-*`, `stone-500`, `evidence-*`,
 * `signal-*`, `null-*`, `destructive-*`) are preserved — every class already
 * in the app keeps compiling — but their values are re-derived from the
 * Beautiful UI neutrals above so the whole app shifts to the new language.
 */

/* ------------------------------------------------------------------ */
/* Semantic themes (Beautiful UI verbatim, except where AA required tuning) */
/* ------------------------------------------------------------------ */

/** Light theme — keys are emitted as bare CSS vars (`--page`, `--ink-2`, ...). */
export const themeLight = {
  /* Surface ladder */
  page: "#fafafb",
  canvas: "#f1f2f3",
  surface: "#ffffff",
  inset: "#f7f8f9",
  hover: "#f4f5f6",
  "hover-2": "#e7e9eb",
  /* Ink ladder */
  ink: "#1f2124",
  "ink-2": "#62656b",
  /** Decorative/disabled glyphs ONLY — fails AA on white by design. */
  "ink-3": "#9a9da3",
  /* Hairlines + fields */
  line: "#ecedef",
  "line-strong": "#e0e2e5",
  field: "#f2f2f3",
  stripe: "#49494913",
  "stripe-bg": "#f5f5f5",
  /* Accent */
  accent: "#0285ff",
  /** Accent as text — AA on white/page. */
  "accent-ink": "#0161c1",
  "accent-tint": "#e9f3ff",
  /* Semantic hues (fills / meters / large glyphs) */
  green: "#189a4d",
  "green-tint": "#e8f5ed",
  orange: "#ef720c",
  "orange-tint": "#fdf1e5",
  red: "#e3474c",
  "red-tint": "#fcecec",
  /* Semantic hues as TEXT (tuned darker than Beautiful UI to clear AA on
     white AND on the matching tint). */
  "green-ink": "#0d6332",
  "orange-ink": "#7d4508",
  "red-ink": "#9d2a2e",
  /* Tooltip (inverted surface) */
  "tooltip-bg": "#25272b",
  "tooltip-fg": "#f6f7f8",
  "tooltip-muted": "#a5a8ad",
  "tooltip-border": "#3a3c40",
} as const;

/** Dark theme — same keys, applied under `.dark` / `[data-theme="dark"]`. */
export const themeDark = {
  page: "#17181a",
  canvas: "#1c1d1f",
  surface: "#232427",
  inset: "#1f2022",
  hover: "#2a2b2e",
  "hover-2": "#313236",
  ink: "#f2f3f4",
  "ink-2": "#a5a8ad",
  "ink-3": "#6c6f75",
  line: "#2e3033",
  "line-strong": "#3a3c40",
  field: "#2b2c2f",
  stripe: "#ffffff0e",
  "stripe-bg": "#1b1c1e",
  accent: "#3d9aff",
  "accent-ink": "#7ec0ff",
  "accent-tint": "#3d9aff29",
  green: "#3dbb72",
  "green-tint": "#3dbb7224",
  orange: "#f68f3c",
  "orange-tint": "#f68f3c24",
  red: "#ee5c61",
  "red-tint": "#ee5c6124",
  "green-ink": "#5cc98a",
  "orange-ink": "#f8a35f",
  "red-ink": "#f2777b",
  "tooltip-bg": "#111214",
  "tooltip-fg": "#f2f3f4",
  "tooltip-muted": "#a5a8ad",
  "tooltip-border": "#2e3033",
} as const;

export type ThemeName = "light" | "dark";
export type SemanticTokenKey = keyof typeof themeLight;
export type SemanticTheme = Record<SemanticTokenKey, string>;

export const semanticThemes: Record<ThemeName, SemanticTheme> = {
  light: themeLight,
  dark: themeDark,
} as const;

/* ------------------------------------------------------------------ */
/* Legacy scales — names preserved, values re-derived from Beautiful UI */
/* ------------------------------------------------------------------ */

/** Deep inks — text ladder on light surfaces (ramped from `ink`/`ink-2`). */
export const ink = {
  /** Primary text. 16.1:1 on white (AAA). */
  950: "#1f2124",
  900: "#25272b",
  800: "#33363c",
  700: "#45484e",
  /** Secondary text — AA on every light surface incl. hover-2. */
  600: "#4b4e55",
  /** = Beautiful UI `ink-2`. */
  500: "#62656b",
  /** Disabled / placeholder — tuned to clear AA (≈ 4.9:1 on page). */
  400: "#6a6d74",
  /** Decorative borders / meters. */
  300: "#b9bcc1",
  200: "#d7d9dc",
  /** = `hover-2`. */
  100: "#e7e9eb",
  /** = `hover`. */
  50: "#f4f5f6",
} as const;

/** Paper tones — surface ladder aliases. */
export const paper = {
  /** = `surface`. */
  50: "#ffffff",
  /** = `page`. */
  100: "#fafafb",
  /** = `canvas`. */
  200: "#f1f2f3",
  /** = `hover-2`. */
  300: "#e7e9eb",
  /**
   * = `line-strong`. Decorative-only divider (WCAG SC 1.4.11 exempt). NEVER
   * use for form borders, focus rings, or actionable chrome — those MUST use
   * `stone.500` or darker to clear the 3:1 non-text floor.
   */
  400: "#e0e2e5",
} as const;

/** Mid-neutral — interactive borders (≥ 3:1 on page). */
export const stone = {
  500: "#7f838a",
} as const;

/**
 * Evidence blue — citation chips, links. Derived from `accent`:
 *   600 = raw accent (fills/graphics, ≥ 3:1), 700 = AA text on white + tint,
 *   800 = AAA text on white (CitationChip target), 950 = deep emphasis.
 */
export const evidence = {
  100: "#e9f3ff",
  600: "#0285ff",
  700: "#0161c1",
  800: "#01458d",
  950: "#0a2e57",
} as const;

/** Signal amber — staleness, warnings. AA on white and on signal-100. */
export const signal = {
  100: "#fdf1e5",
  700: "#7d4508",
} as const;

/** Null-retrieval — deliberately muted neutral. */
export const nullState = {
  100: "#f1f2f3",
  600: "#4b4e55",
} as const;

/** Destructive — confirmations + break-glass. AA on white and on tint. */
export const destructive = {
  100: "#fcecec",
  700: "#9d2a2e",
} as const;

export const colors = {
  ink,
  paper,
  stone,
  evidence,
  signal,
  null: nullState,
  destructive,
} as const;

export type Colors = typeof colors;

/* ------------------------------------------------------------------ */
/* Dark-theme overrides for the legacy scales                          */
/* ------------------------------------------------------------------ */

/**
 * Legacy scales re-pointed for dark mode. Emitted as `.dark { --color-... }`
 * overrides in `dist/tokens.css` so every existing `text-ink-600` /
 * `bg-paper-200` class flips automatically — no component changes needed.
 * The ink ramp inverts; papers map onto the dark surface ladder.
 */
export const colorsDark = {
  ink: {
    950: "#f2f3f4",
    900: "#eceded",
    800: "#dcdee0",
    700: "#c2c4c8",
    600: "#a5a8ad",
    500: "#96999e",
    400: "#8a8d92",
    300: "#4a4c50",
    200: "#3a3c40",
    100: "#313236",
    50: "#2a2b2e",
  },
  paper: {
    50: "#232427",
    100: "#17181a",
    200: "#1c1d1f",
    300: "#313236",
    400: "#3a3c40",
  },
  stone: {
    500: "#8f9297",
  },
  evidence: {
    100: "#1b2c42",
    600: "#3d9aff",
    700: "#7ec0ff",
    800: "#a8d4ff",
    950: "#d8ebff",
  },
  signal: {
    100: "#3a2c1a",
    700: "#f8a35f",
  },
  null: {
    100: "#2a2b2e",
    600: "#a5a8ad",
  },
  destructive: {
    100: "#3c2224",
    700: "#f2777b",
  },
} as const satisfies { [K in keyof Colors]: { [S in keyof Colors[K]]: string } };

export type ColorsDark = typeof colorsDark;
