# GitHub API helpers

## `main-ruleset.json`

Source JSON for a **branch ruleset** on `refs/heads/main` that:

- Blocks **force-push** and **branch deletion** (`non_fast_forward`, `deletion`)
- Requires **pull requests** to merge (0 required approvals by default; adjust in JSON if you want stricter review)
- Requires the **14 status checks** listed in [`.github/workflows/README.md`](../../.github/workflows/README.md) (`CI`, `a11y`, `compose-smoke`, `schema`, `fuzz`)

`strict_required_status_checks_policy` is **false** so PR branches need not be up to date with `main` before merge (squad preference can flip this to `true` later). `do_not_enforce_on_create` is **true** so new branches can be created without every check being present.

### Apply or update (repo admin, `gh` CLI)

```bash
# From repo root (fails with HTTP 422 if a ruleset with the same *name* already exists)
./scripts/github/apply-main-ruleset.sh OWNER/REPO
# e.g. ./scripts/github/apply-main-ruleset.sh kennygeiler/DeployAI
```

Or:

```bash
gh api --method POST repos/OWNER/REPO/rulesets --input scripts/github/main-ruleset.json
```

To **replace** an existing ruleset, delete it in **GitHub → Settings → Rules → Rulesets** (or `gh api -X DELETE repos/OWNER/REPO/rulesets/RULESET_ID`) and POST again, or use **Update repository ruleset** (`PUT /repos/{owner}/{repo}/rulesets/{id}`) with the JSON body and the same `id`.

### Classic branch protection vs. repository ruleset (no double enforcement)

**Do not stack both** on the same default branch. If a **Ruleset** on `main` (Settings → `Rules` → `Rulesets`) and **classic Branch protection** (Settings → `Branches` → *Branch name pattern* for `main`) are both active, you get **duplicate** required checks, confusing merge UIs, and can hit merge blockers. Pick **one** mechanism:

- **Keep the ruleset** (recommended; source: `main-ruleset.json` here) and **remove** the old branch rule: Settings → `Branches` → find `main` (or a matching pattern) → **Delete** the classic protection, **or** edit it to stop requiring the same status checks and PR policy you already have in the ruleset.
- In doubt: the ruleset is listed under `https://github.com/OWNER/REPO/settings/rules` — if `main` is fully covered there, the classic `Branch protection` entry for `main` should be **dropped** so only the ruleset enforces.

## Ruleset on `kennygeiler/DeployAI`

Created 2026-04-24 via API; manage at `https://github.com/kennygeiler/DeployAI/settings/rules` (Repository ruleset).
