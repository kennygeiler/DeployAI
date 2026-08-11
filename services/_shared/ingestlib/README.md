# deployai-ingestlib

Shared ingestion helpers (folded in from the retired `services/ingest` package, ticket B3):

- `deployai_ingestlib.idempotency` — `canonical_ingestion_dedup_key` (FR18 at-most-once canonical writes).
- `deployai_ingestlib.validators` — extraction queue boundary: thread/session units only (FR16).
- `deployai_ingestlib.nfr12_backoff` — exponential visibility/retry schedule for ingestion (NFR12).

Pure helpers, no I/O. Consumed by `services/control-plane` (Slack/Gmail/M365 sync services and the
transcribe-upload worker) via the `deployai-ingestlib` editable path dependency.

```bash
cd services/_shared/ingestlib
uv sync
uv run pytest
```
