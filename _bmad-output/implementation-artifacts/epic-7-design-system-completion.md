# Epic 7 — Design system library (completion note)

**See also (Epic 8):** [`epic-8-implementation-status.md`](./epic-8-implementation-status.md) — strategist walking skeleton and gaps vs `epics.md` Stories 8.1–8.7.

**Stories 7.1–7.14 (components + patterns + hook + Storybook governance):** implemented under `packages/shared-ui` and `apps/web` (Vitest + Storybook; button lint in 7.12; viewport + Chromatic widths + PR artifact comment + Chromatic policy in `storybook.yml` for 7.13–7.14).

| Story | Deliverable |
| ----- | ----------- |
| 7.8 | `TombstoneCard` |
| 7.9 | `AgentOutageBanner` |
| 7.10 | `SessionBanner` (5-min `aria-live` cadence + 1s visual countdown) |
| 7.11 | `EmptyState`, `LoadingFromMemory`, `MemorySyncingGlyph` |
| 7.12 | No raw `<button>` in `apps/web` (ESLint + shadcn `Button`); Pattern stories for buttons + **ExampleForm** + Dialog/Sheet/Popover in `apps/web/src/stories/Patterns/DesignSystemPatterns.stories.tsx` (see governance) |
| 7.13 | `useMobileReadOnlyGate` + `BREAKPOINT_PX` / `MOBILE_READ_ONLY_PX`; Storybook **viewport** toolbar presets + **Chromatic** `viewports` in `apps/web/.storybook/preview.ts` |
| 7.14 | Acceptance bar in `docs/design-system/governance.md`; CI axe via `test-runner`; keyboard/SR docs in `preview.ts`; `storybook.yml` builds, uploads `storybook-static`, Chromatic (strict on `main` push, triage mode on PRs), sticky PR artifact comment |

Full polyglot `turbo` in one image: `infra/docker/Dockerfile.turbo-all` and `scripts/run-turbo-all.sh`.

**7.15** — `@deployai/vpat-aggregator` in `apps/tools/vpat-aggregator` + `.github/workflows/vpat-evidence.yml` (release + `workflow_dispatch`) produce versioned JSON under `artifacts/vpat/`. S3 long-term store remains Epic 13 + AWS OIDC (commented in workflow).

**Test note:** `pnpm turbo run test` requires Python `uv` on PATH for `services/control-plane` (e.g. same environment as CI or `cd services/control-plane && uv run pytest`).

**Retrospective:** [`epic-7-retrospective-2026-04-26.md`](./epic-7-retrospective-2026-04-26.md).
