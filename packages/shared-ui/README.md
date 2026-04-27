# `@deployai/shared-ui`

Epic 7 design-system composites (shadcn + `@deployai/design-tokens` via app globals).

- **7-1** — `CitationChip` (UX-DR4): inline pill, HoverCard preview, context menu, `aria-expanded` for expansion; compose with `EvidencePanel` for inline expansion.
- **7-2** — `EvidencePanel` (UX-DR5): `<article>`, metadata row, `<mark>` highlights from `EvidenceSpan`, loading / degraded / tombstoned, `aria-live` announcements; types from `@deployai/contracts`.
- **7-3** — `PhaseIndicator` (UX-DR6): 32px chrome chip, `aria-live` phase-change announcements, Popover with seven-phase stepper; `phases` + `DEPLOYMENT_PHASES` from `phases.ts` (aligns with Epic 5.4 IDs).
- **7-4** — `FreshnessChip` (UX-DR7): 24px “Synced Ns ago” altimeter; `fresh | stale | very-stale | unavailable` from `freshnessStateForAge` + NFR5 presets in `freshness.ts`; `prefers-reduced-motion` disables transition; `role="status"` + `aria-label`.
- **7-5** — `OverrideComposer` (UX-DR8): three labeled fields + evidence checkboxes; propagation sidecar (stub); Cmd+Enter submit; `role="alert"` error summary; maps to Epic 10 override payload shape later.
- **7-6** — `InMeetingAlertCard` (UX-DR9): floating `complementary` card, peek, `localStorage` position, drag + keyboard nudge; Cmd/Ctrl+Backslash expand + focus trap.
- **7-7** — `ValidationQueueCard` (UX-DR10, FR33): proposal + evidence slot + actions; modify/reject require reason.
- **7-8** — `TombstoneCard` (UX-DR11): removal reason, timestamps, node id, authority, optional appeal.
- **7-9** — `AgentOutageBanner` (UX-DR12, FR46): full-width amber banner; `status` / `alert` roles; status link + optional retry.
- **7-10** — `SessionBanner` (UX-DR42): break-glass vs external-auditor styling; session id + countdown; 5-min `aria-live` cadence.
- **7-11** — `EmptyState`, `LoadingFromMemory`, `MemorySyncingGlyph` (UX-DR22/23/25).
- **7-12** — UX-DR39–41 pattern reference lives in **`apps/web`** (`src/stories/Patterns/DesignSystemPatterns.stories.tsx`: buttons, **ExampleForm**, Dialog/Sheet/Popover); ESLint blocks raw `<button>` outside `src/components/ui` (see `docs/design-system/governance.md`).
- **7-13** — `useMobileReadOnlyGate` (UX-DR38): `true` below 768px by default (mobile read-only for write flows); `BREAKPOINT_PX` / `MOBILE_READ_ONLY_PX` exported for alignment (UX-DR37–38) with `breakpoints.test.ts` regression coverage; Storybook readout in `apps/web/src/stories/Patterns/MobileReadOnlyGate.stories.tsx`; **viewport toolbar + Chromatic widths** in `apps/web/.storybook/preview.ts`.
- **7-14** — CI axe via `@storybook/test-runner` (`a11y.yml`), global keyboard/SR docs in `preview.ts`, Chromatic + sticky PR artifact comment in [`.github/workflows/storybook.yml`](../../.github/workflows/storybook.yml); bar documented in [`docs/design-system/governance.md`](../../docs/design-system/governance.md).
- **Consumers:** add `@source` in `apps/web` `globals.css` for Tailwind v4 to scan this package; Storybook lives in `apps/web`.
- **Buttons (policy):** `apps/web` enforces shadcn `<Button>` (Story 7.12). This package stays **app-agnostic** and may use native `<button>` where a host `Button` is not available; keep minimum touch targets and pass Storybook + `a11y.yml` (axe).

```bash
cd packages/shared-ui
pnpm run build
pnpm run test
```
