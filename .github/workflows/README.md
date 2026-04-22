# `.github/workflows/` — DeployAI CI/CD inventory

This directory holds the GitHub Actions workflows that enforce DeployAI's compliance-native build posture. Every workflow here maps to one or more NFRs from the PRD and is the runtime enforcement layer for controls that would otherwise be documentation-only.

---

## Current workflows (Story 1.2)

| Workflow | Trigger | Purpose | Compliance control(s) | Status |
|---|---|---|---|---|
| `ci.yml` | PR against `main`; push to `main` | Toolchain guard, smoke suite, source-tree SBOM, Grype CVE scan, Dependency Review | NFR62 (SBOM), NFR65 (CVE), Story 1.1 deferred AC4 + AC5 | active |
| `release.yml` | Tag push matching `v*.*.*`; `workflow_dispatch` | Signs + attests release artifacts (cosign keyless, SLSA v1.0 provenance) | NFR63 (signing), NFR64 (SLSA L2) | scaffolded; dormant until Story 1.3 lands buildable workspaces |

Dependabot (`.github/dependabot.yml`) runs weekly across npm, pip, gomod, cargo, and github-actions ecosystems — keeping every dependency and every workflow action SHA fresh. That configuration is the 5th-ecosystem enforcement of NFR65.

---

## Upcoming workflows (owned by future stories)

Not yet present — each is scoped to its owning story to avoid landing half-empty files that confuse future authors:

| Workflow | Owning story | What it will do |
|---|---|---|
| `replay-parity-gate.yml` | Epic 4 (replay-parity harness) | NFR51 — citation-set-identical semantics on LLM model-version upgrades |
| `11th-call-gate.yml` | Epic 5 (citation envelope) | NFR50 — zero hallucinated citations per release candidate |
| `cross-tenant-fuzz.yml` | Epic 1 Story 1.10 | NFR52 — fuzz cross-tenant reads every night; fail CI on any success |
| `a11y-gate.yml` | Epic 1 Story 1.6 | FR44 / NFR43 — axe-core + pa11y + eslint-plugin-jsx-a11y, CI-blocking |

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
