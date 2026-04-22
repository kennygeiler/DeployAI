# Deferred Work

Items surfaced during adversarial review that were intentionally deferred (not in the current story's scope, pre-existing issues, or intentional V1 trade-offs). Each entry notes where it goes next.

---

## Deferred from: code review of story-1-1-init-pnpm-turborepo-monorepo-scaffold (2026-04-22)

- **~~AC5 CI Node-major guard~~** — ✅ **Resolved by Story 1.2 (2026-04-22).** `ci.yml` `toolchain-check` job asserts `node --version` matches `^v24\.` and `pnpm --version == 10.33.0` on every PR and every push to `main`, failing with a clear `::error::` annotation on mismatch. Kept here for audit trail. _Source: Acceptance Auditor AA-01._

- **~~Machine-verifiable AC4 proof~~** — ✅ **Resolved by Story 1.2 (2026-04-22).** `ci.yml` `smoke` job runs the exact Story 1.1 completion-notes suite (`install → turbo build/lint/typecheck/test → prettier --check`) on every PR as six separate steps — mechanical enforcement, not prose assertion. Kept here for audit trail. _Source: Acceptance Auditor AA-03._

- **Browser-workspace `tsconfig` override pattern** — `tsconfig.base.json` uses `module: "nodenext"` + `moduleResolution: "nodenext"`. Next.js App Router and Tauri React frontends require `"bundler"`. Story 1.3's per-workspace `tsconfig.json` must override both. Add an explicit section to Story 1.3's Dev Notes covering this. _Source: Edge Case Hunter ECH-02 (High)._

- **`verbatimModuleSyntax` + CJS default-import tension** — Any workspace importing a CommonJS library via `import foo from 'foo'` will hit TS errors. The fix is `import * as foo from 'foo'` syntax. Cover in Story 1.3's tsconfig setup guidance and mention common CJS libs in the dev-notes. _Source: Edge Case Hunter ECH-06._

- **Per-workspace ESLint configs** — Root `eslint.config.mjs` has `globals.node` only. A future `apps/web/` (Next.js) that doesn't add its own workspace-level `eslint.config.mjs` will flag `window`, `document`, `fetch`, etc. as undefined. Story 1.3's per-workspace setup must include workspace-level ESLint configs with `globals.browser` for browser targets. _Source: Edge Case Hunter ECH-09._

- **Markdown format gate** — `.prettierignore` excludes `*.md` per spec (preserving manual prose formatting). Trade-off: CRLF / inconsistent heading levels / table drift in Markdown go undetected. Accept the gap at V1. Revisit if drift becomes measurable; alternatives: `markdownlint-cli2` (CI-only, doesn't auto-format) or narrow exclusion (allow Prettier on `docs/**` but not `_bmad-output/**`). _Source: Blind Hunter BH-07 + Edge Case Hunter ECH-11._

- **Windows dev-machine portability** — `package.json` `clean` script uses `rm -rf`; no `.gitattributes` means Windows `git autocrlf=true` can override `.editorconfig` LF. V1 is macOS-first per architecture.md (Tauri Edge Agent V1 is macOS-only). Revisit post-GA when Windows is a supported dev environment. _Source: Blind Hunter BH-08 + Edge Case Hunter ECH-08._

- **`engines.node <25.0.0` upper bound** — Intentional V1 guardrail to prevent Node 25 surprises until validated. Needs a revisit story (or a GH issue) when Node 25 reaches the point of adoption. Most likely forcing function: Story 1.2's CI will reveal whether the Node 25 warning becomes an error under `engine-strict=true`. _Source: Edge Case Hunter ECH-10._

---

## Deferred from: implementation of story-1-2-baseline-ci-cd-with-supply-chain-signing (2026-04-22)

- **SARIF-based merge gate for Medium / High CVE findings** — Story 1.2's `cve-scan` job uploads Grype SARIF to GitHub's Security tab and blocks merges only on **Critical** (per NFR65). **Medium** and **High** findings currently surface as warnings + sticky PR comment but don't hard-fail CI. When the security team formalizes a stricter threshold (e.g., StateRAMP 3PAO asks for `high` blocking), re-wire `severity-cutoff` + add a codeql-action required-check status. Track in a follow-up story or Epic 1 retrospective. _Source: Story 1.2 implementation self-review._
