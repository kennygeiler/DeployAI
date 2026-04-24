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

**Avoid duplicate enforcement:** if legacy **Branch protection** rules on `main` are still enabled, consider removing them so only the ruleset applies (Settings → Branches → Branch protection, or the classic UI).

## Ruleset on `kennygeiler/DeployAI`

Created 2026-04-24 via API; manage at `https://github.com/kennygeiler/DeployAI/settings/rules` (Repository ruleset).
