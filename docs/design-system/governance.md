# Design system governance (Epic 7, UX-DR43)

## In scope

- **Custom composites** live in `packages/shared-ui` and are re-exported from `src/index.ts`.
- **Storybook** for visual and interaction review lives in `apps/web/src/stories/` (including `Patterns/` for UX-DR39–41).
- **Accessibility:** `a11y.yml` and `eslint-plugin-jsx-a11y` on `apps/web`; Storybook addon-a11y during `build-storybook` / review.
- **Breakpoints (UX-DR37–38):** Tailwind defaults; `useMobileReadOnlyGate()` in `@deployai/shared-ui` gates write flows on viewports under 768px.

## Out of scope in-repo (follow production program)

- **Chromatic** / per-PR visual baselines and **VPAT evidence S3 publishing (7.15)** require org accounts and release process — track in Epic 13.
- **ESLint “no raw `<button>`”** (Story 7.12) is deferred to avoid churn across `apps/web` until a codemod lands; prefer shadcn `<Button>` for new work.

## Review bar

Every new `shared-ui` composite ships with: unit tests in `packages/shared-ui`, Storybook stories in `apps/web`, and README bullets in `packages/shared-ui/README.md`.
