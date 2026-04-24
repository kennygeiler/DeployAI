# `deployai-cartographer`

Epic 4 **Story 4-1** stub LangGraph and Postgres checkpointing tests.

- `src/cartographer/stub_graph.py` — 3-node graph, canned `CitationEnvelopeV01` payloads.
- `migrations/checkpoints.sql` — notes; real DDL comes from `langgraph-checkpoint-postgres`’s `AsyncPostgresSaver.setup()`.
- `deployai_checkpointer` (`../_shared/checkpointer`) — `async_postgres_saver`, `checkpointer_thread_id`.

```bash
uv sync
uv run pytest
PYTEST_ADDOPTS= uv run pytest tests/integration/ -m integration  # Docker
```
