# Story 6-3 — Oracle phase-gated retrieval + CCM + Null-Result (done)

**Epic:** 6 · **FRs:** FR22, FR23, FR24

## Shipped

- New Python service **`services/oracle`** (`deployai-oracle`): `oracle_retrieve()` in `src/oracle/retrieve.py`.
- Retrieval path: `llama_index` `BaseRetriever` (expected to be wrapped with `llama_citation_adapter.CitationValidatingRetriever` for FR27 envelopes), `QueryBundle(request.query_text)`.
- **Gating:** `node.metadata["tenant_id"]` and `["deployment_phase"]` (nodes missing `deployment_phase` are dropped).
- **Ranking:** deterministic `contextual_fit_score` from retriever score, envelope `confidence_score`, phase fit, optional `recency` metadata.
- **CCM:** `corpus_confidence_marker` ∈ {high, medium, low, null} from the max contextual score of kept nodes; **null** when nothing phase-appropriate remains.
- **Null-Result:** explicit `ExplicitNullResult(reason=...)` when the marker is null — no substitution from other phases.
- **FR23 ambiguity:** `OracleRetrievalRequest.phase_ambiguous` + optional `ambiguous_phases` returns a **union** of matches, each `OracleItem` carrying `deployment_phase`.

## Tests

- `services/oracle/tests/test_retrieve.py` — high CCM, medium band, null (wrong phase / wrong tenant), phase-ambiguity union, drop without `deployment_phase`.

## Follow-ups (not this story)

- Wire a real **pgvector** retriever + ingest-time `deployment_phase` / `tenant_id` on nodes; performance and HNSW tuning.
- Story **6-4:** 3-item budget + ranked-out footer at the Oracle response boundary.
