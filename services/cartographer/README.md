# `deployai-cartographer`

Epic 4 **Story 4-1** stub LangGraph and Postgres checkpointing tests, plus **Epic 6 / Story 6-1 (FR15)** mission-relevance triage.

- `src/cartographer/triage.py` — deterministic relevance score in `[0, 1]` from tenant phase, declared objectives, and event fields (no LLM; triage is cheap and precedes extraction).
- `src/cartographer/metrics.py` — Prometheus `cartographer_triage_outcomes_total` (per `tenant_id`, `phase`, `outcome=passed|triaged_out`); use `rate()` in dashboards for a triage *rate* view.
- Default relevance threshold: **0.3** (overridable on `TriageContext`).
- **Story 6-1 (FR15):** triage (see `triage.py`). **Logs:** with `DEPLOYAI_CARTOGRAPHER_TRIAGE_LOG_JSON=1`, the one-line JSON line omits message bodies. **By default, `event_id` and `tenant_id` in that JSON are 16-char SHA-256 digests (not raw UUIDs).** Set `DEPLOYAI_CARTOGRAPHER_TRIAGE_LOG_IDENTIFIERS=raw` (or `full` / `plain`) only if you need correlators in log pipelines. (See root `.env.example`.)
- **Story 6-2 (FR20):** `src/cartographer/extract.py` — `extract_stub` (deterministic: entities, optional pairwise relationship when ≥2 entities, keyword heuristics for blockers and candidate learnings), `extraction_bundle_to_persist_dict` (full JSON for entities + relationships + blockers + learnings), `bundle_fingerprint` (includes those fields for replay). `src/cartographer/llm_extract.py` — `extract_map_reduce_llm` (Anthropic by default; inject `completer(chunk)->str` in tests; class-level mock on `AnthropicProvider.chat_complete` in `tests/test_llm_extract_mock.py`). Control plane: `cartographer_extraction_persist` appends `cartographer.extraction` with dedupe. Integration test: `services/control-plane/tests/integration/test_cartographer_extraction_persist.py` + `email_thread` fixture. **NFR48 load hook:** from this directory, `uv run python -m cartographer.benchmark` with `**--chars N`** (synthetic size) and `**--mode stub|llm**`: `stub` runs `extract_stub` on a long synthetic thread; `llm` runs `extract_map_reduce_llm` with an **empty-JSON in-process completer** (measures map-reduce + parse overhead only; **not** live model latency; no API key).
- **Downstream (Epic 6):** phase-gated Oracle retrieval and Corpus-Confidence Markers live in `**services/oracle/`** (Story 6-3+), not in this package.

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