# Design system governance (Epic 7, UX-DR43)

## In scope

- **Custom composites** live in `packages/shared-ui` and are re-exported from `src/index.ts`.
- **Storybook** for visual and interaction review lives in `apps/web/src/stories/` (including `Patterns/` for UX-DR39–41).
- **Accessibility:** `a11y.yml` and `eslint-plugin-jsx-a11y` on `apps/web`; Storybook addon-a11y during `build-storybook` / review.
- **Breakpoints (UX-DR37–38):** Tailwind defaults; `useMobileReadOnlyGate()` in `@deployai/shared-ui` gates write flows on viewports under 768px.

## Story 7-13 — Responsive Storybook + Chromatic widths

- **Toolbar viewports** — `apps/web/.storybook/preview.ts` extends Storybook 10’s built-in **`storybook/viewport`** presets (`MINIMAL_VIEWPORTS` + DeployAI keys: 360, 820, 1100, 1440 CSS px) so every story can be spot-checked at mobile / tablet / laptop / desktop widths without a separate addon package.
- **Chromatic snapshots** — the same file sets `parameters.chromatic.viewports: [360, 768, 1024, 1280, 1440]` so visual baselines track Tailwind-aligned breakpoints (see `packages/shared-ui/src/breakpoints.ts`).
- **Hook** — `useMobileReadOnlyGate` + tests remain the write-flow gate below `md` (768px).

## Story 7-14 — Storybook governance (CI + review)

- **axe on every story (CI):** [`a11y.yml`](../../.github/workflows/a11y.yml) `storybook-a11y` runs `build-storybook`, serves `storybook-static`, and executes **`@storybook/test-runner`** with `postVisit` axe (`apps/web/.storybook/test-runner.ts`) using the same WCAG tag list as `preview.ts` → **≥ 1 axe pass per story render** on default viewport.
- **Keyboard + SR bar (docs):** global `parameters.docs.description.component` in `preview.ts` states the keyboard and screen-reader review expectations for all stories (per-story `docs.description.story` is still encouraged for composites with non-trivial interaction).
- **Chromatic policy:** [`.github/workflows/storybook.yml`](../../.github/workflows/storybook.yml) — with `CHROMATIC_PROJECT_TOKEN`, **push to `main`** runs Chromatic **without** `--exit-zero-on-changes` (post-merge regressions fail CI). **Pull requests** use `--exit-zero-on-changes` so open PRs stay mergeable while diffs are accepted in Chromatic’s UI (flip to strict on PRs by editing that workflow when the team is ready).
- **PR review URL:** the workflow uploads the **`storybook-static`** artifact on every run and adds/updates a **sticky bot comment** on same-repo PRs with a link to the workflow run (download artifact). Chromatic remains the hosted UI when the token is configured.

## Optional / org-owned (enable when ready)

- **Chromatic secret:** add repository secret `CHROMATIC_PROJECT_TOKEN` to enable the steps above; leave unset to skip Chromatic only (build + artifact + PR comment still run).
- **VPAT evidence (7.15):** [`apps/tools/vpat-aggregator/`](../../apps/tools/vpat-aggregator) writes a versioned JSON stub under `artifacts/vpat/`. [`.github/workflows/vpat-evidence.yml`](../../.github/workflows/vpat-evidence.yml) runs on `workflow_dispatch` and on `release: published` and uploads that folder as a workflow artifact; an **S3 sync** block is commented until `AWS` OIDC, bucket, and program sign-off (Epic 13 / infra) exist.

- **ESLint “no raw `<button>`”** (Story 7.12): `no-restricted-syntax` in `apps/web/eslint.config.mjs` on `src/**` (shadcn primitives under `src/components/ui/**` are lint-ignored, so the Button file is exempt). New code should use shadcn `<Button>`.
- **CI / merge (path-gated jobs):** `schema`, `fuzz`, and `compose-smoke` use a `prep` + `paths-filter` pattern so the heavy job is **skipped** (success) on irrelevant PRs instead of leaving required checks as **“expected”** — see [`.github/workflows/README.md`](../../.github/workflows/README.md) §Required checks.

## Pattern stories (UX-DR39–41, Story 7.12)

Host Storybook under `apps/web/src/stories/Patterns/` (shadcn primitives are app-scoped):

- [`DesignSystemPatterns.stories.tsx`](../../apps/web/src/stories/Patterns/DesignSystemPatterns.stories.tsx) — button hierarchy, canonical **ExampleForm** stack (Cmd/Ctrl+Enter submit), Dialog (`role="alertdialog"` for destructive mock) + Sheet + Popover.
- [`MobileReadOnlyGate.stories.tsx`](../../apps/web/src/stories/Patterns/MobileReadOnlyGate.stories.tsx) — live readout for `useMobileReadOnlyGate` (UX-DR38 / Story 7-13); resize the viewport across 768px to verify.

These stories run through the same **`@storybook/addon-a11y`** + **viewport** + **Chromatic** parameters as the rest of the catalog (`apps/web/.storybook/preview.ts`).

## Review bar

Every new `shared-ui` composite ships with: unit tests in `packages/shared-ui`, Storybook stories in `apps/web`, and README bullets in `packages/shared-ui/README.md`.
