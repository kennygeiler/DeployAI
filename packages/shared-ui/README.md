# `@deployai/shared-ui`

Epic 7 design-system composites (shadcn + `@deployai/design-tokens` via app globals).

- **7-1** — `CitationChip` (UX-DR4): inline pill, HoverCard preview, context menu, `aria-expanded` for expansion; compose with `EvidencePanel` for inline expansion.
- **7-2** — `EvidencePanel` (UX-DR5): `<article>`, metadata row, `<mark>` highlights from `EvidenceSpan`, loading / degraded / tombstoned (placeholder until 7-8), `aria-live` announcements; types from `@deployai/contracts`.
- **7-3** — `PhaseIndicator` (UX-DR6): 32px chrome chip, `aria-live` phase-change announcements, Popover with seven-phase stepper; `phases` + `DEPLOYMENT_PHASES` from `phases.ts` (aligns with Epic 5.4 IDs).
- **Consumers:** add `@source` in `apps/web` `globals.css` for Tailwind v4 to scan this package; Storybook lives in `apps/web`.

```bash
cd packages/shared-ui
pnpm run build
pnpm run test
```
