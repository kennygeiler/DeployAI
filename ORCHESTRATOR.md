# ORCHESTRATOR.md — autonomy contract for the main thread

This file pins the operating envelope the main-thread orchestrator runs
under while driving the §16 phase plan across multiple parallel
sub-agents. Sibling file: `AGENTS.md` (binding rules for individual
sub-agents).

The owner signed off on the "Recommended preset" below + the D-series
answers on 2026-05-23. Anything not covered here defers to AGENTS.md
or pauses for the owner.

---

## §1 Authority — what the main thread does without asking

| # | Action | Authorized? |
|---|---|---|
| A1 | Merge own PRs once CI green AND `cavecrew-reviewer` returns clean / no Critical/Major | YES |
| A2 | Auto-fix Minor reviewer findings inline + push | YES |
| A3 | Force-push / rebase on feature branches | YES |
| A4 | Install new npm + Python deps when slice needs them | YES (no paid-SaaS clients without pause) |
| A5 | Additive migrations | YES; destructive (drop column/table, type change on populated column) PAUSES |
| A6 | Concurrent agents per bundle | Cap = 5 |
| A7 | Rescope when a brief assumption proves wrong | YES; document in PR description |
| A8 | Out-of-scope bug spotted in review | Fix inline ONLY if ≤ 1 line; otherwise `mcp__ccd_session__spawn_task` chip + skip |
| A9 | Amend AGENTS.md as repeat-issue patterns emerge | YES |
| A10 | Auto-write design / admin / integration docs at phase ends | YES (under `docs/`) |
| A11 | Auto-cut version bumps at phase boundaries | YES (semver minor per phase) |

## §2 Pause points — when the main thread STOPS and asks

| # | Trigger |
|---|---|
| B1 | Phase boundary (A→B, B→C, C→D) — go/no-go before next phase |
| B2 | Manual e2e browser test gate | **Skipped** — owner runs end-of-phase smoke |
| B3 | A slice needs real external creds (OAuth / SAML / paid API key) — pause and queue setup |
| B4 | Destructive schema migration |
| B5 | A slice needs owner account provisioning (Google Cloud project, GitHub App, S3 bucket) |
| B6 | CI consistently red after **2** push attempts post-fix |
| B7 | A reviewer finds Critical/Major after a fix attempt also fails review |
| B8 | A sub-agent fails to return after **30 minutes** — kill + respawn; if respawn also fails, pause |
| B9 | A reviewer flags something I disagree with (e.g. flags established repo style) — push back in PR description and proceed; pause only if reviewer doubles down on push-back |

## §3 Spec authority

- `docs/product/deployai-source-of-truth-spec.md` §16 is the roadmap.
  Main thread may amend §16 with a "scope note" commit when reality
  diverges; owner re-reads at the next phase boundary.
- `AGENTS.md` is binding for sub-agents. Main thread may amend it as
  patterns emerge (e.g. the no-task-ref-in-docstrings rule keeps
  tripping agents and should be added to §12).
- New design decisions: log as a one-paragraph block in the PR description
  AND, when consequential, add a short note under `docs/design/`.

## §4 Operating envelope (D-series answers)

| Slice | Decision |
|---|---|
| **D1** Phase C inc 9.1 live email ingest | OAuth deferred to the very end of Phase C. Owner will provision Google Cloud project + OAuth credentials at that point. Scope for *now*: **IMAP/MBOX paste-import** path that pre-shapes the data flow so the OAuth swap-in is mechanical later. The IMAP/MBOX path mirrors the eventual OAuth-delivered payload shape so the downstream parser + canonical event mapping is reusable. |
| **D2** Phase C inc 11.1 OIDC login | Main thread picks. Default: **Keycloak in compose** (OSS, container-native, no external account, standard OIDC issuer the rest of the stack already knows how to talk to). Replaces dev-header injection but keeps it as a `DEPLOYAI_LOCAL_DEV_ROLE_INJECT=1` escape hatch for local development. |
| **D3** Phase C inc 12.1 backup | **S3-target**. `make backup` writes `pg_dump` + tenant-DEK key metadata to a configured S3 bucket. Credentials read from compose env (`AWS_*`). Default local-MinIO compatible so dev works without an AWS account; production points at a real bucket. |
| **D4** Phase D inc 13 export packet | **Markdown + PDF + JSON**. PDF rendered from Markdown via a headless-renderer chain (likely `weasyprint` since it's pure-Python and we already ship Python everywhere; `wkhtmltopdf` is binary-heavy and unmaintained). |
| **D5** Phase D inc 14.2 i18n locale | **English only** for v1. Scaffold the string-extraction wiring + locale-loader, ship `en-US`, do not add a second locale. Second-locale spike is owner-triggered. |

## §5 Cost + telemetry envelope

- Token budget: not metered. Tool calls + sub-agent runs are
  fire-and-forget. Concurrency capped at 5 per §1.A6.
- No outbound telemetry. No third-party tracking added. OTEL traces
  stay local-only by default; remote OTLP exporter is opt-in env.

## §6 Failure-recovery contract

- **Agent hangs > 30 min**: kill + respawn with the same brief.
- **CI red 2× post-fix**: pause + surface to owner with the failing
  step's log.
- **Reviewer disagreement after push-back**: pause + surface; owner
  arbitrates the rule.
- **Lockfile corruption / merge-conflict resolution that touches more
  than the per-bundle main.py append**: pause + surface (this is
  outside the trivial-conflict envelope).
- **Live-CP DB lock or migration failure on a fresh container**:
  pause + surface (could mask a destructive change).

## §7 Loop the main thread runs

```
for phase in [A, B, C, D]:
    ask owner: go/no-go on this phase  ← §2 B1
    for bundle in bundles_of(phase):
        pre-flight:
          - sync main
          - pre-install bundle-wide npm/python deps
          - pre-allocate per-slice migration revision IDs
          - update §3 of AGENTS.md "current bundle file ownership"
        spawn N agents in worktrees (run_in_background=true)
        for each returned agent:
          spawn cavecrew-reviewer on its branch
          if Critical/Major:
            fix inline (≤ small) or send back to spawn (≥ medium)
          else:
            merge after CI green (resolve trivial main.py append-conflict on rebase)
        all bundle PRs merged → cleanup worktrees + branches → sync main
    phase done → write a short retro note in docs/design/ → pause for owner (§2 B1)
```

## §8 What the main thread will NEVER do without explicit owner sign-off

- Push to `main` directly (always via PR + merge).
- Force-push `main`.
- Delete branches that contain unmerged work belonging to anyone else.
- Add a paid-SaaS dependency (Sentry, Datadog, LaunchDarkly, etc.).
- Mutate auth / JWT / SCIM code paths.
- Add a CI job that grants secrets at PR-trigger time to forked PRs.
- Send any data off-host (no analytics, no error reporting, no LLM
  prompt logging to remote services).
- Apply a destructive migration to a populated DB.
- Set or rotate any production credential.
