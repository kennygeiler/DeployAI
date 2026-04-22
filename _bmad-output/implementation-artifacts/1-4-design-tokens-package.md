# Story 1.4: Design tokens package (`packages/design-tokens/`)

Status: ready-for-dev

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a **UX designer**,
I want a single `packages/design-tokens/` package exposing colors, spacing, typography, shadows, radii, and elevation tokens consumable from both TypeScript and CSS,
so that no surface is ever built with hardcoded values and the calm-authority aesthetic is enforced via tooling.

**Satisfies:** `UX-DR1` (tokens foundation), `UX-DR2` (typography system), `AR1` (first `packages/*` workspace), `NFR28` (WCAG 2.1 AA contrast floor).

---

## Acceptance Criteria

### Epic-source (from `_bmad-output/planning-artifacts/epics.md#Story-1.4`)

**AC1.** `packages/design-tokens/src/tokens.ts` exports `colors` (neutral/ink/paper/stone scales + evidence-blue + signal-amber + destructive — **no primary green**), `spacing` (4px-base scale `0 / 0.5 / 1 / 1.5 / 2 / 3 / 4 / 6 / 8 / 12 / 16 / 24`), `typography` (Inter + IBM Plex Mono families with display/heading/body/small/micro scale), `shadows`, `radii`, `elevation`.

**AC2.** The package emits `dist/tokens.css` with matching CSS custom properties — `--color-ink-950`, `--color-paper-100`, `--color-evidence-700`, `--space-4`, `--radius-md`, `--shadow-sm`, `--font-family-sans`, `--font-family-mono`, `--text-body-size`, `--text-body-line-height`, etc.

**AC3.** `packages/design-tokens/src/tokens.test.ts` verifies every color pair used in body text meets **WCAG AA** contrast (≥ 4.5:1) via `wcag-contrast`. At minimum, the test asserts: `ink-950 / paper-100`, `ink-800 / paper-100`, `ink-600 / paper-100`, `ink-400 / paper-100` (disabled — must still be ≥ 4.5:1), `evidence-700 / paper-100`, `signal-700 / paper-100`, `null-600 / paper-100`, `destructive-700 / paper-100`, and the inverted pairs used for chips (`paper-100 / evidence-700`, etc.).

**AC4.** `apps/web`'s Tailwind config extends from tokens via `@import "@deployai/design-tokens/tailwind"` — **no hardcoded colors/spacing** in `tailwind.config.ts` (or equivalent `@theme` block in `globals.css`).

**AC5.** A Storybook story `Foundations/Tokens.stories.tsx` renders the palette, type ramp, and spacing scale for design review.

**AC6.** `UX-DR1` and `UX-DR2` are satisfied and referenced in the story file header. ✅ (see header above)

### Cross-cutting (wiring, Turbo, CI, governance)

**AC7.** `packages/design-tokens/` is a valid pnpm workspace — discoverable by the root `pnpm-workspace.yaml` glob `packages/*`, with a `package.json` named `@deployai/design-tokens`, `version: 0.0.0`, `private: true`, `type: "module"`, and canonical scripts (`build`, `lint`, `typecheck`, `test`, `clean`). `pnpm install --frozen-lockfile` at the root still reproduces cleanly.

**AC8.** The package is a **library workspace**: `tsconfig.json` extends `../../tsconfig.base.json` and overrides `noEmit: false`, `declaration: true`, `declarationMap: true`, `sourceMap: true`, `outDir: "./dist"` (closes the Story 1.1 deferred guidance about library-workspace emits that ECH-02 flagged).

**AC9.** Dual export surface: `package.json` declares both a JS/TS entry (`"."` conditional exports for `types`, `default`) and a CSS entry (`"./tokens.css"`) and a Tailwind v4 entry (`"./tailwind"` → `./dist/tailwind.css`). The JS entry re-exports from `./dist/index.js`; the CSS entries are consumable as raw CSS.

**AC10.** `dist/tailwind.css` is a Tailwind v4 preset using `@theme` directives (not a JS config — Tailwind v4's CSS-first approach), so `apps/web/src/app/globals.css` can `@import "@deployai/design-tokens/tailwind";` and get all token-derived utility classes (`bg-ink-950`, `text-evidence-700`, `p-4`, `rounded-md`, `shadow-sm`, etc.) automatically.

**AC11.** The build pipeline is deterministic: `pnpm --filter @deployai/design-tokens build` produces `dist/index.js`, `dist/index.d.ts`, `dist/tokens.css`, `dist/tailwind.css`, plus any split per-domain files (optional), with no runtime codegen outside the build step. Build output is reproducible across clean machines — no machine-local paths, timestamps, or user-specific metadata in generated files.

**AC12.** `packages/design-tokens/src/*.test.ts` runs under Vitest via the root `pnpm test` / Turbo `test` task graph and passes. At least one test (`tokens.test.ts` from AC3) must cover contrast; at least one (`tokens.spec.ts` or equivalent) must cover CSS-custom-property name invariants (e.g., every color scale step emits exactly one CSS variable; no typos between `--color-ink-950` and `tokens.ts`'s `colors.ink[950]`).

**AC13.** Storybook lands in `apps/web` using `@storybook/nextjs-vite` 10.x — the framework that supports Next.js 16.2. The setup uses Storybook 10's CSF3 story format and installs only what Story 1.4 needs: `@storybook/nextjs-vite`, `@storybook/addon-a11y`, `@storybook/addon-docs`, `storybook` (CLI). Full shadcn primitive stories are **out of scope** (Story 1.5); the Storybook surface exists only to render `Foundations/Tokens.stories.tsx`.

**AC14.** `@storybook/addon-a11y` is configured with axe-core enabled by default so that the Tokens story shows a11y status in the panel. This front-loads the a11y gate stack that Story 1.6 hardens into a CI-blocking workflow.

**AC15.** `apps/web` gains Storybook scripts: `storybook` (dev), `build-storybook` (static build). Both are added to its `package.json`. `build-storybook` runs under the Turbo `build` task graph (`storybook-static/**` is already listed in `turbo.json#build.outputs`). The Storybook CLI must succeed against a clean repository (`pnpm --filter @deployai/web build-storybook` exits 0).

**AC16.** `apps/web/src/app/globals.css` replaces the Story 1.3 placeholder with the design-tokens import and any minimal `@theme` overrides needed for Inter + IBM Plex Mono font loading via `next/font`. No hardcoded hex colors or raw pixel values remain in `globals.css`, `layout.tsx`, or `page.tsx`.

**AC17.** The Storybook configuration lives under `apps/web/.storybook/` (`main.ts`, `preview.ts`, `manager.ts` optional). `main.ts` registers `@storybook/addon-a11y` + `@storybook/addon-docs`, `framework: "@storybook/nextjs-vite"`, and globs stories from both `apps/web/src/**/*.stories.@(ts|tsx|mdx)` and `packages/design-tokens/src/**/*.stories.@(ts|tsx|mdx)` (so the Tokens story can live alongside its source).

**AC18.** The existing `apps/web/src/app/page.test.tsx` still passes. The Vitest setup is not broken by Storybook's install (Vitest and Storybook share neither config nor port).

**AC19.** Story 1.3's CI contract remains green:
- `pnpm install --frozen-lockfile` reproduces cleanly.
- `pnpm turbo run lint typecheck test build` → all tasks successful (now 5 workspaces × 4 tasks = 20, plus `build-storybook`).
- `pnpm format:check` → clean.
- Story 1.2's 5-job CI gate (toolchain-check, smoke, sbom-source, cve-scan, dependency-review) — all expected statuses preserved.

**AC20.** `docs/repo-layout.md` is updated: the "What Story 1.3 shipped" table gains a new row for `packages/design-tokens/`; the "What this repo does NOT yet contain" list removes the `packages/design-tokens/` bullet.

**AC21.** `docs/design-tokens.md` documents: palette decisions (why no primary green, why evidence-blue, why signal-amber), the 4px spacing ladder, the type ramp with exact sizes/line-heights, the contrast-test methodology, how to add a new token (PR checklist), and the shadcn/ui bridge plan for Story 1.5. Sourced from `ux-design-specification.md` §Foundations (lines 437–466, 511–531, 861–865).

### Scope fence (what this story does NOT do)

**AC22.** Out of scope:

- No shadcn/ui initialization in `apps/web`, no shadcn primitive installs, no `components.json` — Story 1.5.
- No accessibility CI-gate workflow (`eslint-plugin-jsx-a11y` at `error`, axe-playwright, pa11y, `.github/workflows/a11y.yml`) — Story 1.6. Story 1.4 only lands the a11y *addon* in Storybook for local visualization, not CI-blocking.
- No dark-mode token set. Tokens support `prefers-color-scheme` at the CSS-var level where trivial, but the full dark theme is deferred.
- No motion/animation tokens beyond a minimal `--duration-fast / --duration-base` if needed by reduced-motion guidance in `docs/design-tokens.md`. Full motion tokens → Epic 7.
- No shared components (`packages/shared-ui/`). Tokens-only; components arrive in Epic 7.
- No Chromatic integration. Visual regression → Epic 7.
- No token-generation pipeline (Style Dictionary, Theo, etc.). Tokens are hand-authored TS that compile to CSS via a tiny build script, matching the architecture's preference for "author hand-tuned, generate nothing we don't need."

---

## Tasks / Subtasks

### Phase 0 — Prep

- [ ] Pull `main`, verify `pnpm install --frozen-lockfile` + `pnpm turbo run lint typecheck test build` still green after Story 1.3 (baseline). (AC19)
- [ ] Confirm `pnpm-workspace.yaml` still contains `packages/*`; delete `packages/.gitkeep` if present.
- [ ] Re-read `ux-design-specification.md` §Foundations (lines 437–531) for exact token values; `architecture.md` §Monorepo (lines 651–654) for the `packages/design-tokens/` placement; `epics.md#Story-1.4` for the epic-source ACs.

### Phase 1 — Package skeleton + manifest

- [ ] Create `packages/design-tokens/` with `package.json`:
  - `name: "@deployai/design-tokens"`, `version: "0.0.0"`, `private: true`, `type: "module"`.
  - `exports`: `"."` (types + default → `./dist/index.js`), `"./tokens.css"` → `./dist/tokens.css`, `"./tailwind"` → `./dist/tailwind.css`.
  - Scripts: `build` (TS compile + CSS emit), `lint` (`eslint . --max-warnings 0`), `typecheck` (`tsc --noEmit`), `test` (`vitest run --passWithNoTests`), `clean` (`rm -rf dist node_modules`).
  - Dev deps: `typescript`, `vitest`, `wcag-contrast`, `@types/wcag-contrast`, `tsx` (for the CSS-emit script).
  - No runtime deps — package is pure tokens. (AC7, AC9, AC11)
- [ ] `packages/design-tokens/tsconfig.json` extends `../../tsconfig.base.json`; overrides `noEmit: false`, `declaration: true`, `declarationMap: true`, `sourceMap: true`, `outDir: "./dist"`, `rootDir: "./src"`. (AC8 — closes Story 1.1 deferred ECH-02 library-workspace guidance.)
- [ ] `packages/design-tokens/eslint.config.mjs` — flat config, inherits root rules + adds nothing browser-specific (this package has no DOM code).
- [ ] `packages/design-tokens/vitest.config.ts` — `{ test: { environment: "node", include: ["src/**/*.{test,spec}.ts"] } }`.
- [ ] `packages/design-tokens/README.md` — one-paragraph summary + link to `docs/design-tokens.md`.

### Phase 2 — Token source files

- [ ] `src/colors.ts` — export `ink` (950→400), `paper` (100→400), `stone` (500), `evidence` (100, 600, 700), `signal` (100, 700), `null` (100, 600), `destructive` (100, 700). Exact hex values from `ux-design-specification.md` §Color (lines 437–466). (AC1)
- [ ] `src/spacing.ts` — export `space` as object with 4px base: `{ "0": "0", "0_5": "2px", "1": "4px", "1_5": "6px", "2": "8px", "3": "12px", "4": "16px", "6": "24px", "8": "32px", "12": "48px", "16": "64px", "24": "96px" }`. Keep the numeric-string keys so TypeScript consumers can do `spacing["1_5"]`. (AC1)
- [ ] `src/typography.ts` — export `fontFamilies` (`sans`: `"'Inter', system-ui, sans-serif"`, `mono`: `"'IBM Plex Mono', 'Consolas', monospace"`), plus `type` scale: `display`, `heading`, `body`, `small`, `micro` each with `size` and `lineHeight`. Exact ramp per `ux-design-specification.md` §Typography (approx: display 32/40, heading 20/28, body 16/24, small 14/20, micro 12/16). Reading measure: `readingMeasure: { min: "60ch", max: "72ch" }`. (AC1, UX-DR2)
- [ ] `src/shadows.ts` — `shadows.sm`, `shadows.md`, `shadows.lg`. Calm-authority means very subtle: `sm: "0 1px 2px rgba(10, 12, 16, 0.04)"`, etc. (AC1)
- [ ] `src/radii.ts` — `radii.none: "0"`, `radii.sm: "2px"`, `radii.md: "6px"`, `radii.lg: "10px"`, `radii.full: "9999px"`. (AC1)
- [ ] `src/elevation.ts` — `elevation.base: 0`, `elevation.raised: 1`, `elevation.overlay: 10`, `elevation.modal: 100`. (AC1)
- [ ] `src/index.ts` — re-exports everything + a single default `tokens` aggregator. (AC1)

### Phase 3 — CSS + Tailwind preset emitters

- [ ] `scripts/build-css.ts` (invoked by `pnpm build`) — imports from `./src/index.ts` and emits:
  - `dist/tokens.css` — one `:root { --color-ink-950: #0A0C10; --space-4: 16px; ... }` block. Every token in `src/` gets one custom property. (AC2)
  - `dist/tailwind.css` — Tailwind v4 `@theme { --color-ink-950: ...; --spacing-4: 16px; --font-family-sans: ...; ... }` block using the `@theme inline` convention so downstream `@import` consumers just get the theme registered automatically. (AC10)
- [ ] The `build` script chain: `tsc -p tsconfig.json` (emits `dist/index.js` + `.d.ts` + `.map`s) then `tsx scripts/build-css.ts` (emits the two CSS files). Emit order matters because the CSS script imports the compiled JS entry. Alternative: run `tsx` against `src/` directly for both steps. Whichever is simpler. (AC11)
- [ ] All emitted CSS is deterministic — no timestamps, no machine-local paths, no user metadata. (AC11)

### Phase 4 — Tests

- [ ] `src/tokens.test.ts` (AC3):
  - Import `wcag-contrast`'s `hex` function.
  - Assert body-text pairs ≥ 4.5:1: `ink-950/paper-100`, `ink-800/paper-100`, `ink-600/paper-100`, `ink-400/paper-100` (disabled floor).
  - Assert chip pairs ≥ 4.5:1: `evidence-700/paper-100`, `signal-700/paper-100`, `null-600/paper-100`, `destructive-700/paper-100`, `evidence-100/evidence-700` (inverted chip label).
  - Large-text pairs `≥ 3:1` as smoke (none required at V1 but having a `largeText` matrix declared sets the pattern for Epic 7).
  - Assert `ink-950/paper-100 ≥ 7:1` (AAA for `<code>` surfaces).
- [ ] `src/tokens.spec.ts` — invariants (AC12):
  - Every leaf in `colors` has a matching `--color-*` key in the emitted `dist/tokens.css` (regex parse).
  - Every leaf in `spacing` has a matching `--space-*` key in `dist/tokens.css`.
  - No `undefined` / `null` values in any exported object.
  - (The test reads `dist/tokens.css` from disk after a fresh `pnpm build` run in a `beforeAll` — Vitest + node fs is fine.)

### Phase 5 — `apps/web` wiring

- [ ] Add `@deployai/design-tokens: "workspace:*"` to `apps/web/package.json` dependencies.
- [ ] Rewrite `apps/web/src/app/globals.css` (AC4, AC10, AC16):
  ```css
  @import "tailwindcss";
  @import "@deployai/design-tokens/tailwind";
  @import "@deployai/design-tokens/tokens.css";

  html, body {
    font-family: var(--font-family-sans);
    color: var(--color-ink-950);
    background: var(--color-paper-100);
    -webkit-font-smoothing: antialiased;
    -moz-osx-font-smoothing: grayscale;
  }
  ```
- [ ] Update `apps/web/src/app/layout.tsx` to load Inter + IBM Plex Mono via `next/font/google` and expose them as CSS variables the tokens file consumes (`--font-family-sans`, `--font-family-mono`). (AC16)
- [ ] Remove any hardcoded color / spacing classes from `src/app/page.tsx`; replace with token-backed Tailwind utilities (`text-ink-950`, `bg-paper-100`, `p-4`).
- [ ] Verify `pnpm --filter @deployai/web typecheck && pnpm --filter @deployai/web lint && pnpm --filter @deployai/web test && pnpm --filter @deployai/web build` all still pass. (AC18, AC19)

### Phase 6 — Storybook in `apps/web`

- [ ] Install Storybook 10.x (`@storybook/nextjs-vite`, `@storybook/addon-a11y`, `@storybook/addon-docs`, `storybook`) as `apps/web` dev dependencies. Pin exact minors. (AC13)
- [ ] Create `apps/web/.storybook/main.ts`:
  ```ts
  import type { StorybookConfig } from "@storybook/nextjs-vite";
  const config: StorybookConfig = {
    stories: [
      "../src/**/*.stories.@(ts|tsx|mdx)",
      "../../../packages/design-tokens/src/**/*.stories.@(ts|tsx|mdx)",
    ],
    addons: ["@storybook/addon-a11y", "@storybook/addon-docs"],
    framework: { name: "@storybook/nextjs-vite", options: {} },
  };
  export default config;
  ```
  (AC17)
- [ ] Create `apps/web/.storybook/preview.ts`: import `../src/app/globals.css` so stories render with tokens; enable the a11y addon globally. (AC14)
- [ ] Add scripts to `apps/web/package.json`: `"storybook": "storybook dev -p 6006"`, `"build-storybook": "storybook build -o storybook-static"`. Wire `build-storybook` to `build` in the workspace's package-level task chain OR in `turbo.json` as an extra output. Simpler: leave `build-storybook` as a separate pnpm script, not chained to `build`, but ensure CI smoke can call it. (AC15)
- [ ] `packages/design-tokens/src/Tokens.stories.tsx` (story lives in the tokens package, surfaced via Storybook's glob — AC5):
  - `Foundations/Tokens` meta.
  - Three stories: `Palette` (renders color swatches), `TypeRamp` (renders Inter + IBM Plex Mono type scale), `Spacing` (renders the 4px ladder with width visualizations).
  - Each story includes an a11y-addon-friendly DOM (use `<section aria-labelledby="...">`).
- [ ] `pnpm --filter @deployai/web build-storybook` — confirm it exits 0 and produces `storybook-static/index.html`. (AC15)

### Phase 7 — Docs + scope closure

- [ ] `docs/design-tokens.md` per AC21. Include:
  - Palette rationale (calm-authority, no primary green).
  - 4px spacing ladder rationale.
  - Type ramp table with sizes + line-heights + use cases.
  - Contrast methodology (`wcag-contrast` + `tokens.test.ts` coverage).
  - "Adding a new token" checklist (edit `src/*`, add the CSS-var + Tailwind entry, add a test, update this doc).
  - Shadcn bridge plan for Story 1.5 (what `--primary`, `--destructive` etc. will map to).
- [ ] Update `docs/repo-layout.md`:
  - Add row for `packages/design-tokens/` in the Story 1.3 shipped table OR add a new "What Story 1.4 shipped" section (prefer the latter for audit trail continuity).
  - Strike `packages/design-tokens/` from the "not yet contain" list.
  (AC20)

### Phase 8 — Verify + PR

- [ ] Full verification:
  - [ ] `pnpm install --frozen-lockfile` → clean.
  - [ ] `pnpm turbo run lint typecheck test build` → 20+ tasks successful.
  - [ ] `pnpm --filter @deployai/web build-storybook` → exits 0.
  - [ ] `pnpm format:check` → clean.
  - [ ] `pnpm --filter @deployai/design-tokens test` → contrast + invariant tests pass.
- [ ] Commit on `feat/story-1-4-design-tokens`, push, open PR #4.
- [ ] Poll CI; iterate until all 5 jobs green (dependency-review still gated on GHAS).
- [ ] Flip story + sprint-status to `review`; fill Dev Agent Record (debug log, completion notes, file list, change log).

---

## Dev Notes

### Why this story matters

Tokens are the *shape* of every future surface. Landing a single source of truth now means every component — from the shadcn primitives in Story 1.5 to the `CitationChip` in later stories — consumes typed, CSS-variable-backed values instead of hardcoded hexes. When the palette shifts, exactly one file changes. When we add Braille/high-contrast themes later, the variable layer already exists. This is also the first `packages/*` workspace — it sets the convention every future package follows.

### Why Tailwind v4 `@theme`, not a `tailwind.config.ts`

Tailwind v4 is CSS-first. The old JS config is deprecated; `@theme` directives inside CSS are the native extension point. Emitting `dist/tailwind.css` with a single `@theme` block:

1. Works identically in `apps/web`, future `packages/shared-ui`, and any future workspace — no build-step coupling.
2. Survives downstream consumers who haven't adopted Tailwind v4 yet (they ignore `@theme` and still get the `:root` custom properties from `tokens.css`).
3. Is the shape the architecture doc assumes. See `architecture.md` §Tech Stack table (Tailwind v4, CSS-first).

### Why `@storybook/nextjs-vite` 10.x, not the Webpack framework

Per Storybook maintainers ([storybook#32710](https://github.com/storybookjs/storybook/issues/32710), [storybook#33752](https://github.com/storybookjs/storybook/discussions/33752)), Next.js 16 is only supported in `@storybook/nextjs-vite@^10.0.0`. Storybook 9 and the Webpack framework `@storybook/nextjs` do not work with Next 16. Storybook 10 requires Node ≥ 20.19; we're on Node 24, so no constraint violation.

### WCAG contrast test methodology

`wcag-contrast@3.0.0` exports `hex(fg, bg)` returning the ratio. We assert:

- Body text: ≥ 4.5:1 (WCAG AA).
- Large text (≥ 18pt / 14pt bold): ≥ 3:1. We don't have "large text" colors distinct from body, so this column is informational.
- UI / non-text: ≥ 3:1 (NFR28 baseline).
- `CitationChip` specifically targets AAA (≥ 7:1) per `ux-design-specification.md` §856.

The test doesn't try to be exhaustive — it asserts the pairs we *know* ship in the design (from §Foundations). Adding a new color triple means adding a new assertion, and that's a feature, not a burden.

### Anti-patterns (don't do)

1. **Don't** install a token-generation pipeline (Style Dictionary, Theo, `@token-studio/...`). Hand-authored TS → compiled CSS is simpler and the entire repo only needs ~150 tokens at V1.
2. **Don't** add dark mode right now. The variable layer makes it cheap later; cramming it into Story 1.4 blows the scope fence.
3. **Don't** import `globals.css` into every Storybook story individually. `preview.ts` handles it once.
4. **Don't** export a JS-based `tailwind.config.ts` from this package. CSS-first (`@theme`) is the Tailwind v4 way. Any Tailwind consumer that *really* needs a JS shape can synthesize one from `dist/index.js`.
5. **Don't** use Tailwind v3 classnames (`bg-ink-900`) outside this design-tokens scope without verifying the Tailwind v4 `@theme` variable emits the right utility-class name. Tailwind v4 derives `bg-{name}` from `--color-{name}`.
6. **Don't** add any shadcn primitives here. Story 1.5 owns that.

### Known gotchas

1. **`next/font/google` + CSS variables:** `next/font` exposes each font under a `.variable` prop. Assign both to `<html className={`${inter.variable} ${mono.variable}`}>` and then CSS variables `--font-inter` / `--font-mono` are available to downstream CSS. Our tokens CSS then defines `--font-family-sans: var(--font-inter), system-ui, sans-serif;` (fallback chain).
2. **Node loader for TS in `build-css.ts`:** use `tsx` (dev dep already). `node --experimental-strip-types` also works on Node 24 but is less portable.
3. **Vitest + `wcag-contrast` ESM:** the package ships CJS. If the test import fails, `vitest.config.ts` can add `test.server.deps.inline: ["wcag-contrast"]`. Expect this to Just Work; note it here only if needed.
4. **Next font loader + Storybook:** `@storybook/nextjs-vite` 10.x auto-mocks `next/font` (per the Storybook Next.js framework docs). Our Tokens story doesn't use `next/font` directly, so this shouldn't surface; it's a future concern when shadcn button variants render with `next/font` fonts in Story 1.5.
5. **Generated `dist/` — `.gitignore` vs `.prettierignore`:** we already ignore `**/dist/` in both. The CI build regenerates them every run. No state drift.
6. **`exports` + TypeScript module resolution:** if a consumer uses `moduleResolution: "node"` (Tauri's `apps/edge-agent` does not; they use `"bundler"`), our `exports` field resolution may surprise them. Since Tauri's frontend isn't consuming tokens in this story, this is a parking-lot note for Epic 7.
7. **Storybook globs across workspace boundaries:** Vite needs `fs.allow` permission to read files outside the project root. `@storybook/nextjs-vite` handles this when the main.ts `stories` glob uses relative paths; pass via `relative-to-config`-compatible syntax.

### File structure (target)

```
packages/design-tokens/
├── package.json
├── tsconfig.json
├── eslint.config.mjs
├── vitest.config.ts
├── README.md
├── scripts/
│   └── build-css.ts
├── src/
│   ├── index.ts
│   ├── colors.ts
│   ├── spacing.ts
│   ├── typography.ts
│   ├── shadows.ts
│   ├── radii.ts
│   ├── elevation.ts
│   ├── tokens.test.ts
│   ├── tokens.spec.ts
│   └── Tokens.stories.tsx
└── dist/                   # generated by `pnpm build`
    ├── index.js
    ├── index.d.ts
    ├── tokens.css
    └── tailwind.css

apps/web/
├── .storybook/
│   ├── main.ts
│   └── preview.ts
├── package.json             # +deps, +scripts (storybook, build-storybook)
├── src/app/
│   ├── globals.css          # rewritten to @import tokens + tailwind preset
│   ├── layout.tsx           # updated with next/font + token-backed className
│   └── page.tsx             # tokenized utilities

docs/
├── design-tokens.md          # NEW
└── repo-layout.md            # updated
```

---

## Project Structure Notes

- Extends the `packages/*` glob that Story 1.1 declared in `pnpm-workspace.yaml`. This is the first `packages/*` workspace; future packages (`shared-ui`, `citation-envelope`, `tenant-scope`, etc.) follow the same shape.
- `packages/design-tokens/tsconfig.json` is the canonical **library workspace** tsconfig shape — `noEmit: false`, `declaration: true`, `outDir: "./dist"`. Every subsequent package with a compiled entry should clone this pattern. Record this as the template in `docs/repo-layout.md#Adding a new workspace`.
- Storybook landing in `apps/web` (not in the tokens package) is the architectural choice that keeps Storybook as a *consumer* of tokens, not a *host* of them. This matches the Epic 7 plan where Storybook houses every future package's stories, globbed from across the monorepo.
- No conflicts with prior stories. Story 1.3's `apps/web` scaffold remains; we're adding deps + scripts + `.storybook/` + rewriting `globals.css`.

---

## References

- `_bmad-output/planning-artifacts/epics.md` §Epic 1 → §Story 1.4 (lines 644–659) — epic-source ACs.
- `_bmad-output/planning-artifacts/epics.md` §Design Foundation (lines 288–292) — UX-DR1, UX-DR2, UX-DR3.
- `_bmad-output/planning-artifacts/architecture.md` §Monorepo Organization (lines 650–658) — `packages/` tree.
- `_bmad-output/planning-artifacts/ux-design-specification.md` §Foundations (lines 437–531) — exact color/type/spacing values.
- `_bmad-output/planning-artifacts/ux-design-specification.md` §Button hierarchy (lines 861–865) — how tokens feed into shadcn in Story 1.5.
- `_bmad-output/implementation-artifacts/deferred-work.md` — no carry-forward items block this story; ECH-02/06/09 are all resolved.
- Storybook 10 docs (Next.js Vite framework): https://storybook.js.org/docs/get-started/frameworks/nextjs-vite
- Tailwind v4 `@theme` docs: https://tailwindcss.com/docs/theme
- `wcag-contrast` package: https://www.npmjs.com/package/wcag-contrast (v3.0.0, stable since 2019).

---

## Dev Agent Record

### Agent Model Used

_to be filled by dev-story_

### Debug Log References

_to be filled by dev-story_

### Completion Notes List

_to be filled by dev-story_

### File List

_to be filled by dev-story_

---

## Change Log

| Date       | Author | Summary |
|------------|--------|---------|
| 2026-04-22 | bmad-create-story (Kenny + context engine, claude-opus-4.7) | Initial comprehensive story context authored. Loaded `epics.md#Story-1.4`, `ux-design-specification.md` §Foundations (exact palette + type + spacing values), `architecture.md` §Monorepo (packages/ tree), Story 1.3 closeout state (`apps/web` Next.js 16.2 + Tailwind v4 + Vitest scaffold live). Researched latest stable via WebSearch: Storybook 10.x (first Next.js 16-compatible major, per storybook#32710 and discussion#33752), `@storybook/nextjs-vite` 10.x as recommended framework, `wcag-contrast@3.0.0` + `@types/wcag-contrast@3.0.3`. Captured 22 ACs (6 epic-source + 16 cross-cutting covering package manifest, dual-surface exports, Tailwind v4 `@theme` preset, WCAG AA contrast test, Storybook init in apps/web, CI smoke continuity, documentation). 8 task phases, 40+ subtasks. Dev Notes cover Tailwind v4 `@theme` rationale, Storybook 10 / Next 16 compatibility, WCAG methodology, 6 anti-patterns, 7 known gotchas including `next/font` + CSS-var coupling, generated-dist deterministic-output requirement, Storybook glob across workspace boundaries. Scope fence explicitly excludes shadcn (1.5), a11y CI (1.6), dark mode, motion tokens, shared-ui, Chromatic, Style-Dictionary-style token pipelines. Status → ready-for-dev. |
