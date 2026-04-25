# `deployai-oracle`

**Epic 6 — Oracle (Cartographer/Oracle/Strategist).**

- **Story 6-3 (FR22, FR23, FR24):** phase-appropriate retrieval with a **Corpus-Confidence Marker** (CCM), explicit **Null-Result** (no wrong-phase padding), and **phase-ambiguity union** (labels per item). `src/oracle/retrieve.py` — `oracle_retrieve(retriever, request)` runs a citation-validating `llama_index` `BaseRetriever`, enforces `tenant_id` + `deployment_phase` in `node.metadata`, ranks by a deterministic `contextual_fit_score`, and returns `corpus_confidence_marker ∈ {high, medium, low, null}`. Index nodes must include valid `citation_envelope` metadata (use `llama_citation_adapter.CitationValidatingRetriever` as in tests).
- **Story 6-4 (FR22, FR24, FR34):** **3-item hard budget** and **“What I Ranked Out”** at the agent boundary. `src/oracle/budget.py` — `apply_three_item_budget(response, surface=...)` takes an `OracleResponse` and returns `BudgetedOracleResponse` with `primary` (at most three `OracleItem`s) and `ranked_out` (one-line `reason` per suppressed row). In-Meeting Alert and **Morning Digest** use the same cap (`surface="in_meeting_alert"` | `"morning_digest"`). Use `assert_primary_at_most_three(emit)` in contract tests. Composition: `oracle_retrieve` → `apply_three_item_budget`.
- **Story 6-5 (FR25, DP10):** **Suggestions-only** posture. `OracleItem.action_posture` is `Literal["suggestion"]` only. Use `validate_oracle_response_posture` / `validate_budgeted_oracle_posture` before publish. See repo **[`docs/standards/agent-posture.md`](../../docs/standards/agent-posture.md)** for the PR checklist.

**Indexed metadata (required for gating):** `tenant_id` (str), `deployment_phase` (str). Optional: `recency` in ``[0,1]``.

```bash
cd services/oracle
uv sync
uv run pytest
```

Turborepo: `@deployai/oracle` (see `package.json`). **Coverage:** `pnpm run test:cov` from this directory.
