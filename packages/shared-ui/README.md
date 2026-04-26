# `@deployai/shared-ui`

Epic 7 design-system composites (shadcn + `@deployai/design-tokens` via app globals).

- **7-1** — `CitationChip` (UX-DR4): inline pill, HoverCard preview, context menu, `aria-expanded` for expansion; compose with `EvidencePanel` for inline expansion.
- **7-2** — `EvidencePanel` (UX-DR5): `<article>`, metadata row, `<mark>` highlights from `EvidenceSpan`, loading / degraded / tombstoned (placeholder until 7-8), `aria-live` announcements; types from `@deployai/contracts`.
- **7-3** — `PhaseIndicator` (UX-DR6): 32px chrome chip, `aria-live` phase-change announcements, Popover with seven-phase stepper; `phases` + `DEPLOYMENT_PHASES` from `phases.ts` (aligns with Epic 5.4 IDs).
- **7-4** — `FreshnessChip` (UX-DR7): 24px “Synced Ns ago” altimeter; `fresh | stale | very-stale | unavailable` from `freshnessStateForAge` + NFR5 presets in `freshness.ts`; `prefers-reduced-motion` disables transition; `role="status"` + `aria-label`.
- **7-5** — `OverrideComposer` (UX-DR8): three labeled fields + evidence checkboxes; propagation sidecar (stub); Cmd+Enter submit; `role="alert"` error summary; maps to Epic 10 override payload shape later.
- **7-6** — `InMeetingAlertCard` (UX-DR9): 360×240 floating `complementary` card, 40×40 peek, `localStorage` position, header drag + Alt+Arrow nudge; Cmd/Ctrl+\\ expand + focus trap, Esc / Collapse to peek; states `active` | `idle` | `degraded` | `collapsed` | `archived` (archived = unmount).
- **7-7** — `ValidationQueueCard` (UX-DR10, FR33): one proposal + supporting evidence slot + confidence; actions Confirm / Modify / Reject / Defer with `aria-label`s; **modify** and **reject** require a reason string; states `unresolved` | `in-review` | `resolved` | `escalated`.
- **Consumers:** add `@source` in `apps/web` `globals.css` for Tailwind v4 to scan this package; Storybook lives in `apps/web`.

```bash
cd packages/shared-ui
pnpm run build
pnpm run test
```

