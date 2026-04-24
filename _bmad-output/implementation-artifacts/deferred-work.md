# Deferred Work

Items surfaced during adversarial review that were intentionally deferred (not in the current story's scope, pre-existing issues, or intentional V1 trade-offs). Each entry notes where it goes next.

---

## Deferred from: code review of story-1-1-init-pnpm-turborepo-monorepo-scaffold (2026-04-22)

- **~~AC5 CI Node-major guard~~** — ✅ **Resolved by Story 1.2 (2026-04-22).** `ci.yml` `toolchain-check` job asserts `node --version` matches `^v24\.` and `pnpm --version == 10.33.0` on every PR and every push to `main`, failing with a clear `::error::` annotation on mismatch. Kept here for audit trail. _Source: Acceptance Auditor AA-01._

- **~~Machine-verifiable AC4 proof~~** — ✅ **Resolved by Story 1.2 (2026-04-22).** `ci.yml` `smoke` job runs the exact Story 1.1 completion-notes suite (`install → turbo build/lint/typecheck/test → prettier --check`) on every PR as six separate steps — mechanical enforcement, not prose assertion. Kept here for audit trail. _Source: Acceptance Auditor AA-03._

- **~~Browser-workspace `tsconfig` override pattern~~** — ✅ **Resolved by Story 1.3 (2026-04-22).** `apps/web/tsconfig.json` and `apps/edge-agent/tsconfig.json` both extend `../../tsconfig.base.json` and explicitly override `module`/`moduleResolution` to `"bundler"`. `tsc --noEmit` passes for both via `pnpm turbo run typecheck`. Kept here for audit trail. _Source: Edge Case Hunter ECH-02._

- **~~`verbatimModuleSyntax` + CJS default-import tension~~** — ✅ **Resolved by Story 1.3 (2026-04-22).** Per-workspace tsconfigs inherit `verbatimModuleSyntax: true` from the base; `apps/web` and `apps/edge-agent` compile cleanly under `tsc --noEmit` because all imports are type-only or ESM-native. Re-address in later stories only if a new workspace hits a CJS default-import failure. _Source: Edge Case Hunter ECH-06._

- **~~Per-workspace ESLint configs~~** — ✅ **Resolved by Story 1.3 (2026-04-22).** `apps/web/eslint.config.mjs` uses `eslint-config-next` (which ships `globals.browser`); `apps/edge-agent/eslint.config.mjs` declares `globals.browser` + `globals.node` explicitly and wires `@typescript-eslint` + `react-hooks`. Both pass `pnpm lint` with `--max-warnings 0`. _Source: Edge Case Hunter ECH-09._

- **Root ESLint downgraded 10.x → 9.39.4** — During Story 1.3 implementation, `eslint-config-next@16.2.4` transitively depends on `eslint-plugin-react@7.37.5` / `eslint-plugin-jsx-a11y@6.10.2` / `eslint-plugin-import@2.32.0`, none of which support ESLint 10 yet (ESLint 10 removed `context.getFilename()` etc.). Root + per-workspace `eslint` dep pinned to `^9.39.4`. Revisit when the Next.js / eslint-plugin-react stacks ship ESLint 10-compatible releases. _Source: Story 1.3 implementation self-review._

- **Markdown format gate** — `.prettierignore` excludes `*.md` per spec (preserving manual prose formatting). Trade-off: CRLF / inconsistent heading levels / table drift in Markdown go undetected. Accept the gap at V1. Revisit if drift becomes measurable; alternatives: `markdownlint-cli2` (CI-only, doesn't auto-format) or narrow exclusion (allow Prettier on `docs/**` but not `_bmad-output/**`). _Source: Blind Hunter BH-07 + Edge Case Hunter ECH-11._

- **Windows dev-machine portability** — `package.json` `clean` script uses `rm -rf`; no `.gitattributes` means Windows `git autocrlf=true` can override `.editorconfig` LF. V1 is macOS-first per architecture.md (Tauri Edge Agent V1 is macOS-only). Revisit post-GA when Windows is a supported dev environment. _Source: Blind Hunter BH-08 + Edge Case Hunter ECH-08._

- **`engines.node <25.0.0` upper bound** — Intentional V1 guardrail to prevent Node 25 surprises until validated. Needs a revisit story (or a GH issue) when Node 25 reaches the point of adoption. Most likely forcing function: Story 1.2's CI will reveal whether the Node 25 warning becomes an error under `engine-strict=true`. _Source: Edge Case Hunter ECH-10._

---

## Deferred from: implementation of story-1-2-baseline-ci-cd-with-supply-chain-signing (2026-04-22)

- **SARIF-based merge gate for Medium / High CVE findings** — Story 1.2's `cve-scan` job uploads Grype SARIF to GitHub's Security tab and blocks merges only on **Critical** (per NFR65). **Medium** and **High** findings currently surface as warnings + sticky PR comment but don't hard-fail CI. When the security team formalizes a stricter threshold (e.g., StateRAMP 3PAO asks for `high` blocking), re-wire `severity-cutoff` + add a codeql-action required-check status. Track in a follow-up story or Epic 1 retrospective. _Source: Story 1.2 implementation self-review._

---

## Epic 3 backlog follow-ups (2026-04-23)

Tracked after Epic 3 close; not reopening story rows in `sprint-status.yaml` until scheduled.

| Follow-up | Description |
|----------|---------------|
| **Web upload UX** | First-party `/upload` (or edge-agent) flow beyond presign/complete API. |
| **Real ASR** | Wire `DEPLOYAI_UPLOAD_ASR_MODE=transcribe` to AWS Transcribe (or provider) in `control_plane.workers.transcribe_upload` — current behavior is stub text + log. |
| **S3 lifecycle** | 90-day (or policy-driven) raw object retention on the upload bucket (NFR33). |
| **Citation E2E** | End-to-end extraction/citation from `upload.transcript` + `asr.transcript` into downstream surfaces. |
| **Gmail/Slack staging** | Broader live-OAuth and soak tests when those integrations are customer-critical. |

**Retrospective notes:** `epic-3-retrospective-2026-04-23.md` · **PRD alignment:** `epics.md` / voice-upload story.

---

## Deferred from: code review of story-1-5-shadcn-ui-initialization-and-theme-bridging (2026-04-22)

- **Narrow `exactOptionalPropertyTypes: false` to vendored primitives only** — Story 1.5 scopes the opt-out to the whole `apps/web` tsconfig to unblock the 3 shadcn/Radix prop-surface errors (`context-menu.tsx`, `dropdown-menu.tsx`, `sonner.tsx`). The opt-out is broader than the "vendored code only" discipline the story otherwise maintains: `ExampleForm.tsx`, stories, and future app code under `apps/web/src/**` now skip the strict flag too. Follow-up: split `apps/web/tsconfig.json` into a strict parent (covers app code) + a reference-project tsconfig that includes `src/components/ui/**` with the flag disabled, so the strict guard comes back for user-authored code. Low priority — Story 1.5's authored code already passes `tsc --noEmit` against the strict flag (verified pre-relaxation), and the narrowing is cosmetic. Revisit when a future Epic adds more app-authored forms/components and drift becomes measurable. _Source: Acceptance Auditor on code review of Story 1.5; also flagged in Story 1.5 Open Questions line 899._
