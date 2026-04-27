# `.github/workflows/` — DeployAI CI/CD inventory

This directory holds the GitHub Actions workflows that enforce DeployAI's compliance-native build posture. Every workflow here maps to one or more NFRs from the PRD and is the runtime enforcement layer for controls that would otherwise be documentation-only.

---

## Current workflows

| Workflow | Trigger | Purpose | Compliance control(s) | Status | Landed in |
|---|---|---|---|---|---|
| `ci.yml` | PR against `main`; push to `main` | Toolchain guard, **smoke** (`pnpm turbo` …, including `test` for `@deployai/cartographer` / Epic 4-1), then job **Control plane (integration)** — `uv run pytest tests/integration/ -m integration` in `services/control-plane` (Docker + Postgres testcontainers, Epic 2/3 and related). SBOM, Grype CVE, Dependency Review in other jobs. | NFR62 (SBOM), NFR65 (CVE), FR27 contract gate, Story 1.1 deferred AC4 + AC5; integration coverage for control-plane; cartographer via turbo test for AR6 / Story 4-1 | active | Story 1.2 |
| `release.yml` | Tag push matching `v*.*.*`; `workflow_dispatch` | Signs + attests release artifacts (cosign keyless, SLSA v1.0 provenance) | NFR63 (signing), NFR64 (SLSA L2) | scaffolded; dormant until Story 1.3 lands buildable workspaces | Story 1.2 |
| `a11y.yml` | PR against `main`; push to `main` | 4-job a11y gate: `jsx-a11y` lint, `storybook-a11y` test-runner, `playwright-a11y` E2E axe, `pa11y` axe + htmlcs | FR44, NFR28, NFR41, NFR42, NFR43, AR25 | active | Story 1.6 |
| `compose-smoke.yml` | PR against `main` (path-filtered on `infra/**`, `services/**`, `apps/web/Dockerfile`, `packages/authz/**`, `packages/design-tokens/**`, `Makefile`, `pnpm-lock.yaml`); push to `main` | Brings up the full local stack (postgres + pgvector/pgcrypto, redis, minio, freetsa-stub, control-plane, web) via `make dev`, runs `make dev-verify`, fails if wall-clock exceeds 30 min | NFR67, NFR68, NFR77 | active | Story 1.7 |
| `schema.yml` | PR against `main` (path-filtered on `services/control-plane/**`, `infra/compose/postgres/**`, the workflow itself); push to `main` | Runs the canonical-memory schema integration tests against a fresh `pgvector/pgvector:pg16` testcontainer — append-only trigger, UUID v7 defaults, partial-unique identity-attribute history, supersession CHECK, enum rejection, lifecycle transitions, tombstone bytea roundtrip | FR1–3, FR5, NFR74 | active; **required on `main`** (see §3) | Story 1.8 |
| `fuzz.yml` | PR against `main` (path-filtered on `services/**`, `services/_shared/tenancy/**`, `services/control-plane/alembic/versions/**`, the workflow itself); push to `main` | Cross-tenant isolation fuzz harness — seeds 3 synthetic tenants × 50 rows × 8 canonical tables, then runs **6 attack classes** (baseline RLS reads, no-scope reads, SET ROLE escalation, ORM escape hatches, cross-tenant writes, SQLi payloads) ≥ 500 attempts/table. GUC-override (class 3) is intentionally omitted — application-layer defense only, cannot be meaningfully exercised by a raw-SQL fuzzer. JSON report at `artifacts/fuzz/cross-tenant-report.json`; see [docs/security/cross-tenant-fuzz.md](../../docs/security/cross-tenant-fuzz.md) | NFR52, FR72 | active; **required on `main`** (see §3) | Story 1.10 |
| `cartographer-benchmark.yml` | PR/push to `main` (path `services/cartographer/**`); `workflow_dispatch`; weekly (Mon 06:00 UTC) | Runs `uv run python -m cartographer.benchmark` in **stub** and **llm** (mock completer) modes on synthetic char targets — regression signal for NFR48 extract paths; not a live-model p95 | NFR48, Epic 6 Story 6.2 | active | Epic 6 retro |
| `storybook.yml` | PR or push to `main`; `workflow_dispatch` | `pnpm turbo run build-storybook` for `@deployai/web`, uploads `storybook-static` artifact; **Chromatic** when `CHROMATIC_PROJECT_TOKEN` is set (strict on `push` to `main`, `--exit-zero-on-changes` on PRs); sticky PR comment with artifact link (same-repo PRs) | Epic 7 Stories 7-13–7-14, UX-DR43 | active | Epic 7 |
| `vpat-evidence.yml` | `workflow_dispatch`; `release: published` | Runs `@deployai/vpat-aggregator` to emit VPAT evidence JSON; uploads `artifacts/vpat` (S3 block commented until AWS + bucket) | Epic 7.15 / Epic 13 VPAT | active (stub + artifact); S3 when infra ready | Epic 7 |

Dependabot (`.github/dependabot.yml`) runs weekly across npm, pip, gomod, cargo, and github-actions ecosystems — keeping every dependency and every workflow action SHA fresh. That configuration is the 5th-ecosystem enforcement of NFR65.

---

## Upcoming workflows (owned by future stories)

Not yet present — each is scoped to its owning story to avoid landing half-empty files that confuse future authors:

| Workflow | Owning story | What it will do |
|---|---|---|
| `replay-parity-gate.yml` | Epic 4 (replay-parity harness) | NFR51 — citation-set-identical semantics on LLM model-version upgrades |
| `11th-call-gate.yml` | Epic 5 (citation envelope) | NFR50 — zero hallucinated citations per release candidate |
When you add one of the above, mirror the conventions documented below and update the tables in this file in the same PR.

---

## Conventions (must-follow)

### 1. Pin every external action by full 40-char commit SHA

Tag-pinned actions are mutable; a compromised maintainer can retag `v5` to point at malicious code. SHA-pinned actions are immutable. This is a StateRAMP SA-12 control.

Format:

```yaml
- uses: actions/checkout@93cb6efe18208431cddfb8368fd83d5badbf9bfd # v5.0.0
```

The trailing `# vX.Y.Z` comment is **required** — Dependabot's `github-actions` ecosystem reads that comment and bumps both the SHA and the comment atomically when a new release ships.

To resolve a SHA for a given tag:

```bash
gh api repos/<owner>/<repo>/git/refs/tags/<tag> --jq '.object.sha'
# or for repos that only publish major-version pointers (rare):
gh api repos/<owner>/<repo>/commits/<tag> --jq '.sha'
```

### 2. Workflow-level `permissions:` is `contents: read`; jobs opt in

Never grant write scopes at the workflow level. Jobs that need `id-token: write` (OIDC), `attestations: write` (SLSA), `packages: write` (OCI push), or `pull-requests: write` (sticky comments) declare them locally on that job only. This is least-privilege per AC10.

### 2b. GitHub Advanced Security (GHAS) dependency

Two `ci.yml` features require **GitHub Advanced Security** on private repos:

- `cve-scan → Upload SARIF to Security tab` — uploads Grype findings to Security → Code scanning.
- `dependency-review` job — PR-diff CVE + license review.

Both are gated by the repo-level Actions variable **`GHAS_ENABLED`**. When this variable is unset (default), they skip cleanly (gray checkmark in PR UI, no red failure). This makes the private-no-GHAS workflow clean out of the box — no noisy failures.

**Activation (when GHAS is enabled, likely during StateRAMP procurement):**

1. Enable GHAS on the repo: Settings → Security and analysis → enable "Dependency graph", "Dependabot alerts", "Code scanning", "Secret scanning".
2. Set the variable: Settings → Secrets and variables → Actions → Variables → New repository variable → name `GHAS_ENABLED`, value `true`.
3. The next PR run will exercise both features automatically.

**Compliance posture in the meantime:** NFR65 (CVE scanning) is still enforced by the Grype JSON triage step in `cve-scan` — Critical findings fail CI, High findings warn + post a sticky PR comment. The GHAS-gated features only add the "Security tab" surface and PR-diff scope; they don't replace the core gate.

### 3. Fork-PR safety (AC11)

PRs from forks cannot access `GITHUB_TOKEN` with write scopes or use OIDC to request signing identities. Any step that calls `cosign`, `actions/attest-*`, or posts write-scope API calls **must** be guarded:

```yaml
- if: github.event_name != 'pull_request' || github.event.pull_request.head.repo.full_name == github.repository
```

`release.yml` is naturally safe — it's tag-triggered, and forks can't push tags to our repo. `ci.yml` is also naturally safe — it contains no supply-chain-write steps. Future workflows that combine fork-PR runs with write-scope steps (e.g., a PR-time attestation job) MUST add the guard above.

### 4. Concurrency

- PR workflows: `cancel-in-progress: true`. Superseded commits should not pile up compute cost.
- `main` push / tag / release workflows: `cancel-in-progress: false`. Let them complete.

### 5. Timeouts

Every job declares `timeout-minutes:`. Default to 20 for smoke-style jobs, 30 for build-and-sign, 5 for pure checks. No job may run without a ceiling.

### 6. Runner pinning

Pin the runner version explicitly (e.g., `runs-on: ubuntu-24.04`, not `ubuntu-latest`). When GitHub deprecates a runner image, a pinned workflow fails loudly; an unpinned one silently changes behavior.

---

## Required checks on `main`

Branch protection on `main` must require the exact set of check-runs
below before a PR can merge. The strings are the literal `<workflow>
/ <job-name>` GitHub displays on the PR status UI — copy them verbatim
into Settings → Branches → Branch protection rule → "Require status
checks to pass before merging" (or **Rulesets** → **Require status checks**).

After this doc’s 2026-04-23 update, add any **new** strings below that are
not yet in your repo’s rule (especially `Control plane (integration)`,
`Ingest (pytest)`, `canonical-memory-schema`, `cross-tenant-fuzz`).

**Repository ruleset contexts:** the API and mergeability use the **check-run job `name`**
as reported on the PR and by `gh pr view N --json statusCheckRollup` — not the
`{workflow} / {job}` form shown in some older examples. The 14 required checks are:

From `ci.yml` (workflow `name: CI` — job `name` values only):

- `Toolchain (Node 24 + pnpm 10.33.0)`
- `Smoke (install / build / lint / typecheck / test / format)`
- `Control plane (integration)`
- `Ingest (pytest)`
- `SBOM (source — SPDX + CycloneDX)`
- `CVE scan (grype)`
- `Dependency review (PR diff)`

From `a11y.yml` (job `name` values):

- `jsx-a11y`
- `storybook-a11y`
- `playwright-a11y`
- `pa11y`

From `compose-smoke.yml`:

- `compose-smoke`

From `schema.yml`:

- `canonical-memory-schema`

From `fuzz.yml`:

- `cross-tenant-fuzz`

**Path-gated PR gates** (`schema`, `fuzz`, `compose-smoke`): each workflow
**always runs on `pull_request`** to `main`, but a cheap `prep` job uses
`dorny/paths-filter` to decide whether the heavy job runs. If paths do not
match, the heavy job is **skipped** (not “expected”) — which GitHub counts as
a successful required check, so **docs-only PRs** do not need ruleset
workarounds or no-op workflow nudges. `push` to `main` still uses `on: paths`
for `schema` and `fuzz` to avoid spurious post-merge runs; `compose-smoke`
runs the heavy job on every push (same as before).

**Repository ruleset (automated):** the `main` branch has an active
**ruleset** (status checks + PR-only merge) defined as JSON in
[`scripts/github/main-ruleset.json`](../../scripts/github/main-ruleset.json)
and documented in [`scripts/github/README.md`](../../scripts/github/README.md).
Re-apply with `gh api` per that README. Remove legacy **Branch protection**
rules on `main` if they duplicate this ruleset (Settings → Branches).

> The `ci.yml` names carry parenthetical descriptors for historical
> reasons (Story 1.2) — branch protection matches the literal string,
> so leave them as-is until a dedicated rename PR updates both this
> table and the GitHub branch-protection rule in one commit. The
> `a11y.yml` names were deliberately stabilized (Story 1.6) without
> parentheticals to avoid repeating that lock-in.

Conditionally skipping checks (configured via `if:` in the workflow,
not via branch-protection settings):

- `ci / cve-scan` and `ci / dependency-review` are gated by the
  `GHAS_ENABLED` repository variable (see §2b above). When GHAS is off,
  they report a neutral conclusion — branch protection treats neutral
  as passing. **Do not** mark them as "required" only when GHAS is on;
  the neutral-conclusion pattern handles this transparently.
- PR fork runs skip write-scope steps via the §3 `if:` guard. None of
  the required checks listed above are gated by that guard, so fork
  PRs can still reach mergeable.

**Conventions that protect these strings:**

1. Job `name:` values MUST match the bare patterns above (no
   parenthetical descriptors like `jsx-a11y (static lint)`) so the
   branch-protection matcher is stable across job-body edits. Rename
   the job only when there's a genuine semantic change — and do it in
   a PR that updates this table in the same commit.
2. Workflow `name:` values likewise. `a11y.yml` declares `name: a11y`;
   don't change to `Accessibility` without updating this list AND
   branch protection AND any downstream tooling (VPAT pipeline,
   compliance exports) that greps for the workflow name.
3. When adding a new job to `ci.yml` or `a11y.yml`, default to NOT
   adding it to the required set. Most new jobs are experimental; only
   promote to required after a stabilization window where the job has
   been running on PRs without false positives.

---

## SLSA provenance: why `actions/attest-build-provenance@v4`, not `slsa-github-generator`

The architecture doc (`_bmad-output/planning-artifacts/architecture.md` §"CI/CD") names `slsa-github-generator` as the SLSA L2 provenance tool. As of 2026, GitHub offers a first-class, less-ceremony alternative: **`actions/attest-build-provenance@v4`**.

- It produces a SLSA v1.0 provenance predicate (same predicate format at the output layer).
- It uses GitHub's OIDC + Sigstore under the hood; no long-lived credentials; keyless.
- It writes the attestation to GitHub's attestation storage (visible on the repo's Attestations tab).
- It requires only `id-token: write` + `attestations: write` on the job — no separate reusable workflow call.
- It's maintained by the GitHub Actions team, not a third-party org — relevant for a government-facing product.

Both approaches satisfy NFR64 at SLSA Level 2. If a StateRAMP 3PAO audit requires the specific named tool, the swap is mechanical — the consumers (verifiers) don't care which generator emitted the predicate.

---

## Developer workflow for modifying CI

1. Make the edit on a feature branch.
2. Locally validate YAML: `python3 -c 'import yaml,sys; [yaml.safe_load(open(f)) for f in sys.argv[1:]]' .github/workflows/*.yml .github/dependabot.yml` (pre-commit hook coming in Story 1.5).
3. Optionally run `actionlint` if installed: `brew install actionlint && actionlint .github/workflows/*.yml`.
4. Push the PR. `ci.yml` itself will run on the PR and catch most config errors.
5. For release workflow edits: tag a test-release from the branch (`git tag v0.0.0-test-<name> && git push origin v0.0.0-test-<name>`), verify, then delete the tag.

---

## Cross-reference

- Root product requirements: `_bmad-output/planning-artifacts/prd.md` §"Supply chain" + §"NFR62–NFR65"
- Architecture rationale: `_bmad-output/planning-artifacts/architecture.md` §"CI/CD" + §"Binding Constraints"
- Story 1.2 authoring context: `_bmad-output/implementation-artifacts/1-2-baseline-ci-cd-with-supply-chain-signing.md`
- Carry-forward items from Story 1.1: `_bmad-output/implementation-artifacts/deferred-work.md`
