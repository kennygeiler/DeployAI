# `deployai-cartographer`

Epic 4 **Story 4-1** stub LangGraph and Postgres checkpointing tests.

- `src/cartographer/stub_graph.py` — 3-node graph, canned `CitationEnvelopeV01` payloads.
- `migrations/checkpoints.sql` — notes; real DDL comes from `langgraph-checkpoint-postgres`’s `AsyncPostgresSaver.setup()`.
- `deployai_checkpointer` (`../_shared/checkpointer`) — `async_postgres_saver`, `checkpointer_thread_id`.

```bash
uv sync
uv run pytest
```

Integration test (Postgres in Docker) lives under `tests/integration/`; it is **skipped** if Docker is not running. **Do not** append inline shell comments to pytest commands: a stray `#` can be mistaken for a path and yield `file or directory not found: #`.

To run only integration tests:

```bash
uv run pytest tests/integration/ -m integration
```

To **exclude** integration (faster, unit only), pass an explicit marker:

```bash
uv run pytest -m "not integration"
```
