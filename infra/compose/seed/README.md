# Local seed scripts

Two seed scripts live here. They target different schemas and are used at
different times.

## `seed.sh` — Story 1.7 reference seed (runs automatically on `make dev`)

Populates a `fixtures.*` schema in Postgres with a synthetic tenant + 24
events + a phase row. Used by `make dev-verify` to assert the stack is wired
end-to-end. **Does not seed the real app schema** (`engagements`,
`canonical_memory_events`, `matrix_*`).

If you only want to verify the compose stack is healthy, `make dev` is
enough — it runs this script for you.

## `seed_app.py` — Phase 6.2c app-schema seed (runs on demand)

Creates the data you need to **manually test the product**:

- 1 `app_tenant` (`acme-county-pilot`)
- 3 `app_users` (deployment-team roles: strategist, FDE, biz_dev)
- 1 `engagement` (`Acme County permit-modernization rollout` — gov/policy
  domain, stable UUID `bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb`)
- 3 `engagement_members` (one per team role)
- ~20 `canonical_memory_events` (emails, meeting notes, field notes,
  decision memos — a realistic 7-week deployment slice)
- Triggers Cartographer extraction per event so `matrix_proposals` exist
  before you open the engagement detail page

### Requirements

1. Compose stack already up: `make dev`
2. `infra/compose/.env` contains:
   ```
   DEPLOYAI_LLM_PROVIDER=anthropic
   ANTHROPIC_API_KEY=sk-ant-...
   ```
   Without an Anthropic key the seed still runs, but the stub LLM returns
   no proposals and the matrix stays empty — defeats the purpose.

### Usage

```bash
# First-time bring-up:
make dev
make seed-app

# Open the engagement:
open http://localhost:3000/engagements/bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb

# Re-run (idempotent — events dedupe via dedup_key, proposals dedupe per event):
make seed-app

# Force re-extraction (discards pending proposals and re-runs the LLM — costs $):
make seed-app SEED_APP_ARGS=--force-extract

# Ingest events only, no LLM calls (for offline testing of the UI):
make seed-app SEED_APP_ARGS=--skip-extract
```

### Cost estimate

One full seed run = ~20 LLM calls × ~$0.05 each = **~$1.00** with
Claude 3.5 Sonnet. Re-runs without `--force-extract` cost $0 (cached).

### When to re-seed from scratch

If you want a guaranteed clean slate (different scenario, schema changes,
debugging weird state):

```bash
make dev-down    # drops volumes — wipes DB + MinIO
make dev         # fresh stack
make seed-app    # fresh data
```

`make dev-down` is destructive (drops the volumes). Confirm before running.
