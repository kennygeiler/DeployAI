# `deployai-cartographer`

Epic 4 **Story 4-1** stub LangGraph and Postgres checkpointing tests, plus **Epic 6 / Story 6-1 (FR15)** mission-relevance triage.

- `src/cartographer/triage.py` — deterministic relevance score in `[0, 1]` from tenant phase, declared objectives, and event fields (no LLM; triage is cheap and precedes extraction).
- `src/cartographer/metrics.py` — Prometheus `cartographer_triage_outcomes_total` (per `tenant_id`, `phase`, `outcome=passed|triaged_out`); use `rate()` in dashboards for a triage *rate* view.
- Default relevance threshold: **0.3** (overridable on `TriageContext`).

**Do not paste pytest’s screen report** (the `====` lines, progress bar, or `[100%]`) back into your shell. zsh treats `[…]` as a glob, so you will see `no matches found: [100%]`. **Only run the commands below** (type them or copy a single line with no extra text after it).

- `src/cartographer/stub_graph.py` — 3-node graph, canned `CitationEnvelopeV01` payloads.
- `migrations/checkpoints.sql` — notes; real DDL comes from `langgraph-checkpoint-postgres`’s `AsyncPostgresSaver.setup()`.
- `deployai_checkpointer` (`../_shared/checkpointer`) — `async_postgres_saver`, `checkpointer_thread_id`.

```bash
cd services/cartographer
uv sync
pnpm test
```

Or with `uv` only (same as `pnpm test`):

```bash
uv run pytest
```

**Unit only** (no Docker):

```bash
pnpm run test:unit
```

**Integration only** (Postgres in Docker; skipped if Docker is not running):

```bash
pnpm run test:integration
```

**Do not** put `#` comments on the same line as `uv run pytest` when you paste: if `#` is passed to pytest, you get `file or directory not found: #`. Put comments on a **separate** line, or use `pnpm` scripts above (no comment needed).
