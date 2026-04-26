# Epic 7 retrospective — Design system library

**Date:** 2026-04-26 · **Scope:** `epics.md` / UX-DR4–12, 22–25, 37–43 — components, patterns, Storybook, governance, responsive hook, button lint, VPAT/Chromatic/turbo CI scaffolding (per `epic-7-design-system-completion.md`)

## Outcomes (what shipped in-tree)

- **`packages/shared-ui`:** Citation through primitives 7-1–7-11, `PhaseIndicator` + `phases`, `useMobileReadOnlyGate`, `BREAKPOINT_PX` / `MOBILE_READ_ONLY_PX`, `breakpoints.test.ts`, Vitest across composites.
- **`apps/web`:** Storybook stories for each composite + `DesignSystemPatterns`, ESLint `no-restricted-syntax` banning raw `<button>` in `src/**` (vendored `src/components/ui/**` ignored for lint).
- **CI / dev experience:** `scripts/ci-uv-sync-all.sh` in `ci.yml` smoke; `Dockerfile.turbo-all` + `turbo-ci` + `run-turbo-all.sh`; `storybook.yml` + `vpat-evidence.yml` + `apps/tools/vpat-aggregator` stub; `artifacts/vpat/` gitignored.
- **Hardening during merge:** Prettier on all touched trees; `TombstoneCard` `<dl>` structure for Storybook/axe; `OverrideComposer` checkbox **target-size**; `ExampleForm` `zodResolver(exampleFormSchema as never)` for Zod v4 + Next production build; nudge to `.github/workflows/schema.yml` so **canonical-memory-schema** runs when the ruleset expects it but paths would otherwise skip the workflow.

## What worked well

- **Contract-first types** from `@deployai/contracts` in evidence surfaces kept UI aligned with control-plane and Epic 5 citation shape.
- **Same Storybook + test-runner stack as a11y CI** (`a11y.yml` job 2) caught serious axe issues (definition-list, target-size) before they hit `main`.
- **Polyglot `turbo` + `uv` sync in CI** matches local full-verify scripts — fewer “works on my machine” gaps for Python + Node.

## Learnings and risks

- **Zod v4 vs `@hookform/resolvers` types** are stricter in **`next build`** than in `tsc --noEmit` alone — the `as never` bridge on the schema is intentional until the resolver package aligns; document at call sites, don’t duplicate ad hoc casts.
- **Path-filtered required checks** (`schema.yml`, `fuzz.yml`, etc.) + a ruleset that **always** expects a job name can **block merge** with “expected” until a trivial path in the workflow file is updated — use the nudge in `schema.yml` (or adjust GitHub ruleset “do not require skipped checks” if policy allows).
- **Design system package vs app:** `shared-ui` stays **app-agnostic** and may use native `<button>` where needed; **`apps/web`** is the shadcn enforcement zone — two policies are consistent if documented.
- **Prettier as a hard gate** in smoke caught wide formatting drift across `shared-ui` and stories; treat `pnpm run format:check` as part of the default loop before push.

## Action items (forward)

| Item | Note |
| ---- | ---- |
| **Turborepo `test` output warnings** | Global `test` had `outputs: ["coverage/**"]` while most Vitest tasks write no `coverage/` — set `outputs: []` for `test` to silence “no output files” warnings (trade-off: no Turbo output cache for coverage dirs). |
| **Document path-filtered merge + button policy** | governance + `shared-ui` README. |
| **Chromatic** | Set `CHROMATIC_PROJECT_TOKEN` when program-owned; optional required-check in ruleset only if you want it blocking. |
| **VPAT S3** | Epic 13: OIDC, bucket, uncomment job in `vpat-evidence.yml`. |
| **Epic 8** | Wire primitives into Morning Digest / Phase / Evening Synthesis; replace stubs with real control-plane and agent APIs. |

## Readiness for Epic 8/9/10

- **Surfaces (Epic 8)** can import `@deployai/shared-ui` with tokens already bridged in `apps/web` globals.
- **Queues & in-meeting (Epic 9)** map directly to `ValidationQueueCard` and `InMeetingAlertCard` stories; refine copy and data binding.
- **Overrides (Epic 10)** have `OverrideComposer` payload shape; backend contracts and audit trail follow separately.

## Team sentiment (brief)

- **Friction:** merge blocked until schema job + format + a11y were green — systems worked, but path-filtered rules need a runbook.  
- **Pride points:** a11y CI + design governance make Epic 7 a **reusable** layer for all customer-facing work.

## Follow-up shipped (this change set)

- **`turbo.json`:** `test` task `outputs` cleared to `[]` to remove recurring Turbo warnings when packages do not emit `coverage/`.
- **Docs:** `docs/design-system/governance.md` (CI / path-filtered required checks) and `packages/shared-ui/README.md` (button policy: package vs `apps/web`).
- **Cross-link:** `epic-7-design-system-completion.md` points to this retrospective.
