# Story 7-2 — `EvidencePanel` (done)

**Package:** `packages/shared-ui` — `EvidencePanel` with `retrievalPhase` from `@deployai/contracts`, metadata row (source, timestamp, phase, confidence, supersession), `renderHighlightedBody` + evidence-blue `<mark>`, states `loading` | `loaded` | `degraded` | `tombstoned`, `aria-live="polite"` (sr-only), `aria-busy` while loading. Tombstoned body is a plain-language block until `TombstoneCard` (7-8).

**App:** `apps/web` Storybook `Components/EvidencePanel` (loaded, loading, degraded, tombstoned, async Suspense, chip+panel). **Tests:** 5 in shared-ui (highlight + a11y).
