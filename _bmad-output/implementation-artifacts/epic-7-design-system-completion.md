# Epic 7 — Design system library (completion note)

**Stories 7.1–7.11 (components + primitives):** implemented under `packages/shared-ui` with Vitest + `apps/web` Storybook.

| Story | Deliverable |
| ----- | ----------- |
| 7.8 | `TombstoneCard` |
| 7.9 | `AgentOutageBanner` |
| 7.10 | `SessionBanner` (5-min `aria-live` cadence + 1s visual countdown) |
| 7.11 | `EmptyState`, `LoadingFromMemory`, `MemorySyncingGlyph` |
| 7.13 (hook) | `useMobileReadOnlyGate` |

**7.12** — `apps/web/src/stories/Patterns/DesignSystemPatterns.stories.tsx` documents button hierarchy; full lint gate for raw `<button>` deferred (see `docs/design-system/governance.md`).

**7.14** — `docs/design-system/governance.md` records governance; Chromatic + PR Storybook URL workflows remain program-owned.

**7.15** — VPAT aggregator / S3 evidence pipeline deferred to Epic 13 + infra.

**Test note:** `pnpm turbo run test` requires Python `uv` on PATH for `services/control-plane` (e.g. same environment as CI or `cd services/control-plane && uv run pytest`).
