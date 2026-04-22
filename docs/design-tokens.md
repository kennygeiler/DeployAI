# Design Tokens — `@deployai/design-tokens`

The single source of truth for every color, spacing value, typography
setting, shadow, radius, and elevation used anywhere in DeployAI.
Satisfies `UX-DR1` (foundation tokens) and `UX-DR2` (typography system).

The package is consumed three ways:

| Surface | Import | Use case |
|---|---|---|
| TypeScript | `import { colors, spacing, typography } from "@deployai/design-tokens"` | Typed values in React, tests, or Node scripts. |
| Raw CSS custom properties | `@import "@deployai/design-tokens/tokens.css"` | Any CSS consumer. Emits `--color-ink-950`, `--spacing-4`, `--text-body-size`, etc. at `:root`. |
| Tailwind v4 preset | `@import "@deployai/design-tokens/tailwind"` | Tailwind-idiomatic `@theme` block. `bg-ink-950`, `text-display`, `p-4`, `rounded-md`, `shadow-sm` all derive automatically. |

> **No hardcoded colors, spacing, radii, shadows, or font sizes anywhere
> outside this package.** If you need a new value, add a token.

## Color — calm-authority palette

Neutral-dominant. **No primary green.** Government strategists associate
bright success green with consumer apps; DeployAI uses neutral + glyph for
"resolved" states (see `UX-DR28` color-independence).

| Scale | Range | Purpose |
|---|---|---|
| `ink` | `400`, `600`, `800`, `950` | Text stack on paper. `950` is primary (AAA on `paper-100`). `400` is disabled/placeholder. |
| `paper` | `100`–`400` | Backgrounds and surfaces. `100` = page, `300` = card, `400` = divider. |
| `stone` | `500` | Mid-neutral for borders and subtle chrome. |
| `evidence` | `100`, `600`, `700` | Citation chips, reference links. `700` is AAA on `paper-100`. |
| `signal` | `100`, `700` | Staleness, warnings (amber). `700` is AAA on `paper-100`. |
| `null` (retrieval) | `100`, `600` | Deliberately muted neutral for null-retrieval states. |
| `destructive` | `100`, `700` | Confirmations only. Never pre-selected. |

Rationale:

- **Evidence blue** (`#1F4A8C`) for references anchors the trust
  affordance; it reads as institutional, not corporate.
- **Signal amber** (`#7A5211`) is muted and deep — not the playful yellow
  of a consumer app.
- **Destructive red** (`#9F1A1A`) is reserved for break-glass and
  tombstone confirmations; nothing else carries red fills.

Source: `ux-design-specification.md` §Foundations (lines 437–466).

## Spacing — 4 px ladder

```
0 · 0.5 · 1 · 1.5 · 2 · 3 · 4 · 6 · 8 · 12 · 16 · 24
```

Each step is the multiplier of the 4 px base unit (so `4` = 16 px,
`24` = 96 px). Keys with a fractional component use underscore notation
(`0_5`, `1_5`) so TypeScript consumers can use bracket access:
`spacing["1_5"]`. CSS variables rewrite the underscore as a hyphen:
`--spacing-1-5: 6px;`. Tailwind v4 utilities follow suit: `p-1-5`,
`gap-0-5`.

Only step values from this ladder should appear in CSS output. Any
deviation must land as a new token, not an inline override.

## Typography — Inter + IBM Plex Mono

| Step | Size | Line height | Weight | Use |
|---|---|---|---|---|
| `display` | 2rem / 32 px | 1.25 | 600 | Top-of-page headings (Digest, Phase Tracking). |
| `heading` | 1.25rem / 20 px | 1.4 | 600 | Section headings. |
| `body` | 1rem / 16 px | 1.5 | 400 | Default prose. |
| `small` | 0.875rem / 14 px | 1.43 | 400 | Secondary text, meta. |
| `micro` | 0.75rem / 12 px | 1.33 | 500 | Chip labels, timestamps, legends. |

Families:

- **Sans** — Inter (loaded via `next/font/google`, exposed as
  `--font-inter`, aliased by the tokens as `--font-sans`).
- **Mono** — IBM Plex Mono for citation IDs, timestamps, and code
  (`--font-mono`). Chosen over generic mono for its tabular figures and
  humanist letterforms — legible in dense evidence panels.

Long-form prose (evidence panels, override rationale) is constrained to
the reading measure `--reading-measure-min: 60ch` / `--reading-measure-max:
72ch`. This is the point where reading speed peaks for most fonts.

## Shadows, radii, elevation

Shadows are intentionally subtle — calm-authority aesthetic discourages
heavy drop shadows. Every shadow is an `rgba(ink-950)` layer so it stays
neutral across themes:

| Token | Value | Use |
|---|---|---|
| `shadows.sm` | `0 1px 2px rgba(10,12,16,.04)` + hairline | Card hover, subtle lift. |
| `shadows.md` | `0 2px 4px rgba(10,12,16,.06)` layered | Panels over paper. |
| `shadows.lg` | `0 8px 16px rgba(10,12,16,.08)` layered | Modals, overlays. |
| `shadows.focus` | 2 px outer ring on `paper-100` around `evidence-700` | Focus-visible compositing when an `outline` isn't available. |

Radii run `none → sm (2 px) → md (6 px) → lg (10 px) → full` (pill).

Elevation is a z-index ladder — `base`, `raised`, `overlay`, `dropdown`,
`modal`, `toast`. New layers **must** be added here before use.

## Motion

Minimal for V1:

```
--duration-instant: 0ms
--duration-reducedMotion: 50ms   /* honors prefers-reduced-motion */
--duration-fast: 120ms
--duration-base: 200ms
--easing-standard: cubic-bezier(0.2, 0, 0, 1)
--easing-out: cubic-bezier(0, 0, 0.2, 1)
```

Full motion tokens (per-interaction easing curves, enter/exit durations,
spring physics) arrive in Epic 7.

`prefers-reduced-motion: reduce` is honored globally in `apps/web` —
animations clamp to `--duration-reducedMotion` and iteration counts clamp
to 1 (see `apps/web/src/app/globals.css`).

## WCAG AA contrast — enforced by test

`packages/design-tokens/src/tokens.test.ts` uses
[`wcag-contrast@3`](https://www.npmjs.com/package/wcag-contrast) to assert:

| Pair class | Threshold | Covered |
|---|---|---|
| Body text on `paper-100` | ≥ 4.5:1 (AA) | `ink-950`, `ink-800`, `ink-600`, `evidence-700`, `signal-700`, `null-600`, `destructive-700` |
| Colored label on tinted fill (chips) | ≥ 4.5:1 (AA) | `evidence-700 / evidence-100`, `signal-700 / signal-100`, `null-600 / null-100`, `destructive-700 / destructive-100` |
| Paper label on solid fill (inverted chips) | ≥ 4.5:1 (AA) | `paper-100 / evidence-700`, `paper-100 / destructive-700` |
| AAA targets (`CitationChip`, primary text) | ≥ 7:1 (AAA) | `ink-950 / paper-100`, `evidence-700 / paper-100` |
| Disabled / placeholder (WCAG-exempt but enforced to UI floor) | ≥ 3:1 (UI components) | `ink-400 / paper-100` |
| Non-text UI (hover states, chips-as-UI) | ≥ 3:1 | `evidence-600 / paper-100` |

`ink-400` is exempt from the 4.5:1 body-text threshold by WCAG 2.1 SC 1.4.3
(inactive user-interface components), but we still enforce the 3:1 floor of
SC 1.4.11 (non-text contrast) so placeholder text stays readable for
peripheral vision.

If you add a new color, add the corresponding contrast assertion. The
tokens.test.ts suite is the specification — if a color change breaks it,
fix the color, not the test.

## Build pipeline

```
pnpm --filter @deployai/design-tokens build
├── rm -rf dist
├── tsc -p tsconfig.build.json     # emits dist/*.js + .d.ts + .map
└── tsx scripts/build-css.ts       # emits dist/tokens.css + dist/tailwind.css
```

Everything is deterministic — no timestamps, no machine-local paths, no
user metadata in generated CSS. The build re-runs in CI on every job; no
state persists across machines.

## Adding a new token

1. **Decide the domain.** New color scale? Extend `src/colors.ts`. New
   spacing step? Extend `src/spacing.ts`. New radius? Extend `src/radii.ts`.
2. **Add the value.** Keep the `as const` on the object so TypeScript
   derives literal types.
3. **Re-export from `src/index.ts`** if you added a new named export.
4. **Update the emitter** in `scripts/build-css.ts` if you introduced a
   new token domain (rare — most additions are just new leaves in an
   existing domain).
5. **Add the contrast assertion** (colors only) to
   `src/tokens.test.ts`. The build is NOT complete until this test passes.
6. **Update the invariant test** (`src/tokens.spec.ts`) only if you
   changed the CSS variable naming convention — otherwise it
   auto-covers every new leaf.
7. **Rebuild**: `pnpm --filter @deployai/design-tokens build`. The
   emitted CSS should include your new `--` variable.
8. **Document** the rationale here if the token represents a design
   decision (a new palette scale, a new elevation layer, a new motion
   duration).

## shadcn/ui bridge — Story 1.5

Story 1.5 initialized shadcn/ui in `apps/web` and authored the theme
bridge: a two-layer cascade in `apps/web/src/app/globals.css` that maps
shadcn's semantic CSS variables onto the DeployAI tokens this package
emits. See [shadcn.md](./shadcn.md) for the full initialization contract.

**Layer A (`@layer base :root`)** — aliases shadcn's semantic names onto
DeployAI tokens. Zero literal colors.

```css
@layer base {
  :root {
    /* Surface */
    --background: var(--color-paper-100);
    --foreground: var(--color-ink-950);
    --card: var(--color-paper-200);
    --card-foreground: var(--color-ink-950);
    --popover: var(--color-paper-100);
    --popover-foreground: var(--color-ink-950);

    /* Intent */
    --primary: var(--color-evidence-700);
    --primary-foreground: var(--color-paper-100);
    --secondary: var(--color-paper-200);
    --secondary-foreground: var(--color-ink-800);
    --muted: var(--color-paper-200);
    --muted-foreground: var(--color-ink-600);
    --accent: var(--color-null-100);
    --accent-foreground: var(--color-null-600);
    --destructive: var(--color-destructive-700);
    --destructive-foreground: var(--color-paper-100);

    /* UI chrome */
    --border: var(--color-paper-300);
    --input: var(--color-stone-500);
    --ring: var(--color-evidence-700);

    /* Geometry */
    --radius: var(--radius-md);
  }
}
```

**Layer B (`@theme inline`)** — re-exports the same names back into
Tailwind v4's theme layer so utilities like `bg-primary`,
`text-muted-foreground`, `ring-ring`, and `rounded-md` resolve.

```css
@theme inline {
  --color-background: var(--background);
  --color-foreground: var(--foreground);
  --color-primary: var(--primary);
  --color-primary-foreground: var(--primary-foreground);
  /* …full mapping per shadcn.md */
  --radius-sm: calc(var(--radius) - 4px);
  --radius-md: var(--radius);
  --radius-lg: calc(var(--radius) + 4px);
  --radius-xl: calc(var(--radius) + 8px);
}
```

Three mapping choices worth calling out (full rationale lives in
[shadcn.md](./shadcn.md) §Theme bridge):

- **`--border: var(--color-paper-300)`** — shadcn's "subtle divider"
  wants a surface-tone neutral, not the mid-neutral `stone-500` we
  reserve for high-emphasis UI chrome. `paper-400` is **not** used here
  because the Story 1.4 code review declared it decorative-only (it
  fails the 3:1 SC 1.4.11 non-text floor).
- **`--input: var(--color-stone-500)`** — form field borders are
  high-emphasis UI; `stone-500` clears ≥ 3:1 non-text contrast against
  `paper-100`.
- **`--ring: var(--color-evidence-700)`** — aligns with this package's
  `shadows.focus` (`0 0 0 2px paper[100], 0 0 0 4px evidence[700]`) so
  DOM `outline` focus and `box-shadow` focus agree on color.

The semantic-variable layer means shadcn primitives render in the
DeployAI palette without per-component re-theming, and every component
story in Epic 7 composes correctly.

## Scope fence

**This package does not:**

- Install or configure shadcn/ui (landed in Story 1.5 — see
  [shadcn.md](./shadcn.md) for the initialization contract).
- Ship the axe-core / ESLint a11y / pa11y CI-blocking gates (Story 1.6).
- Publish a dark-mode token set (deferred; variable layer supports it).
- Host visual regression infrastructure (Chromatic, Epic 7).
- Ship shared components (`packages/shared-ui`, Epic 7).
- Run a token-generation pipeline (Style Dictionary et al.) — tokens are
  hand-authored TS that compile to CSS via a small script; the repo does
  not need more than that at V1.

## References

- `_bmad-output/planning-artifacts/epics.md` §Story 1.4 — epic-source ACs.
- `_bmad-output/planning-artifacts/ux-design-specification.md` §Foundations
  (lines 437–531, 861–865) — every concrete value here traces back to that
  spec.
- `_bmad-output/planning-artifacts/architecture.md` §Monorepo Organization
  — the `packages/design-tokens/` position in the workspace tree.
- Tailwind v4 `@theme` docs: <https://tailwindcss.com/docs/theme>
- WCAG 2.1: <https://www.w3.org/TR/WCAG21/>
