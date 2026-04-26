# Story 7-4 — `FreshnessChip` (done)

**Package:** `packages/shared-ui` — `FreshnessChip` (24px, `h-6`) with glyph + text; bands from `freshnessStateForAge` + `FRESHNESS_NFR5_MS` (`digest` / `in_meeting` / `phase_tracking`) or custom `thresholdsMs`. `prefers-reduced-motion` drops the color transition. Vitest: `freshness.test.ts`, `FreshnessChip.test.tsx`, `phases.test.ts`. Storybook: `apps/web/src/stories/Components/FreshnessChip.stories.tsx`.

**Follow-up (Epic 8):** mount in top rail with `PhaseIndicator`; pass `lastSyncedAt` from tenant memory health API when available.
