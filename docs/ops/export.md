# Engagement export packet

`make export ENGAGEMENT=<uuid>` writes a self-contained packet for one
engagement: Markdown, PDF, and a JSON snapshot. Operators use it to share
a deployment's current state with stakeholders outside the app, or to
archive a closed engagement.

## What gets included

- Engagement header — id, name, customer account, current phase, created-at
- Members — engagement-scoped users + their role
- Matrix nodes — every typed entity in the deployment graph
- Matrix edges — every typed relationship
- Insights — Oracle + Master Strategist observations on this engagement
- Recent activity — last 100 `strategist_activity_events` for the tenant

## What is **never** included

- `tenant_llm_configs.api_key` (LLM credentials)
- `tenant_webhooks.signing_secret` (webhook HMAC secrets)
- Tenant DEK key material (export via `dek_metadata` CLI separately)

The aggregator only selects columns named in `gather_engagement` —
nothing else is read from the database.

## Usage

```bash
ENGAGEMENT=<uuid> \
DATABASE_URL=postgresql+psycopg://deployai:deployai@localhost:5432/deployai \
DEPLOYAI_TENANT_ID=<uuid> \
make export
```

Or invoke the CLI directly for more control:

```bash
cd services/control-plane
uv run python -m control_plane.cli.export \
  --engagement <uuid> \
  --tenant-id <uuid> \
  --out-dir ./packet/<uuid> \
  --database-url postgresql+psycopg://...
```

Files land in `--out-dir` (default `./packet/<engagement>/`):

- `markdown.md` — human-readable Markdown
- `packet.pdf` — same content rendered via WeasyPrint
- `data.json` — machine-readable mirror of the aggregator output

## Exit codes

- `0` — packet written
- `1` — DB error or engagement not found for the given tenant
- `2` — missing configuration (`--database-url`, `--tenant-id`, bad UUID)
