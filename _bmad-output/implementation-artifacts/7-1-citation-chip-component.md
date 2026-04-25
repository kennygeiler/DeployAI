# Story 7-1 — `CitationChip` (done)

**Package:** `packages/shared-ui` — `CitationChip` with `inline` | `standalone` | `compact` density; visual states `default` | `overridden` | `tombstoned` plus `expanded` + focus ring; HoverCard (250 ms) preview; ContextMenu (View evidence, Override, Copy link, Cite in override); composite `aria-label` for SR.

**App wiring:** `apps/web` depends on workspace `@deployai/shared-ui`; `globals.css` uses `@source` for Tailwind v4 to scan the package. Storybook: `src/stories/Components/CitationChip.stories.tsx` (matrix + keyboard/SR copy). Chromatic baselines are deferred to Story 7-14 per sprint plan.
