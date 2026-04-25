# `deployai-oracle`

**Epic 6 / Story 6-3 (FR22, FR23, FR24):** phase-appropriate retrieval with a **Corpus-Confidence Marker** (CCM), explicit **Null-Result** (no wrong-phase padding), and **phase-ambiguity union** (labels per item).

- `src/oracle/retrieve.py` — `oracle_retrieve(retriever, request)` runs a citation-validating `llama_index` `BaseRetriever`, enforces `tenant_id` + `deployment_phase` in `node.metadata`, ranks by a deterministic `contextual_fit_score`, and returns `corpus_confidence_marker ∈ {high, medium, low, null}`. Index nodes must include valid `citation_envelope` metadata (use `llama_citation_adapter.CitationValidatingRetriever` as in tests).

**Indexed metadata (required for gating):** `tenant_id` (str), `deployment_phase` (str). Optional: `recency` in ``[0,1]`.

```bash
cd services/oracle
uv sync
uv run pytest
```

Turborepo: `@deployai/oracle` (see `package.json`).
