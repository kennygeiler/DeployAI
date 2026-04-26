# Design system governance (Epic 7, UX-DR43)

## In scope

- **Custom composites** live in `packages/shared-ui` and are re-exported from `src/index.ts`.
- **Storybook** for visual and interaction review lives in `apps/web/src/stories/` (including `Patterns/` for UX-DR39–41).
- **Accessibility:** `a11y.yml` and `eslint-plugin-jsx-a11y` on `apps/web`; Storybook addon-a11y during `build-storybook` / review.
- **Breakpoints (UX-DR37–38):** Tailwind defaults; `useMobileReadOnlyGate()` in `@deployai/shared-ui` gates write flows on viewports under 768px.

## Optional / org-owned (enable when ready)

- **Chromatic (7.14):** [`.github/workflows/storybook.yml`](../../.github/workflows/storybook.yml) always builds and uploads a `storybook-static` artifact. Add repository secret `CHROMATIC_PROJECT_TOKEN` to run the optional Chromatic step; leave unset to skip. PR comments / GitHub app integration use Chromatic’s own docs.
- **VPAT evidence (7.15):** [`apps/tools/vpat-aggregator/`](../../apps/tools/vpat-aggregator) writes a versioned JSON stub under `artifacts/vpat/`. [`.github/workflows/vpat-evidence.yml`](../../.github/workflows/vpat-evidence.yml) runs on `workflow_dispatch` and on `release: published` and uploads that folder as a workflow artifact; an **S3 sync** block is commented until `AWS` OIDC, bucket, and program sign-off (Epic 13 / infra) exist.

- **ESLint “no raw `<button>`”** (Story 7.12): `no-restricted-syntax` in `apps/web/eslint.config.mjs` on `src/**` (shadcn primitives under `src/components/ui/**` are lint-ignored, so the Button file is exempt). New code should use shadcn `<Button>`.
- **CI / merge (path-filtered jobs):** Branch rules on `main` can require e.g. **`canonical-memory-schema`** while [`.github/workflows/schema.yml`](../../.github/workflows/schema.yml) only runs when certain paths change. If GitHub shows the check as **“expected”** and blocks merge, either enable **“do not require status checks that are skipped”** in the ruleset, or add a no-op nudge to that workflow file (see the comment in `schema.yml`). Same idea applies to other path-gated workflows documented in [`.github/workflows/README.md`](../../.github/workflows/README.md).

## Review bar

Every new `shared-ui` composite ships with: unit tests in `packages/shared-ui`, Storybook stories in `apps/web`, and README bullets in `packages/shared-ui/README.md`.
