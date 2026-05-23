# DeployAI — Matrix extraction agent (Cartographer)

| | |
| --- | --- |
| **Status** | Design / decision record. Phase 6 increment **6.2b**. |
| **Date** | 2026-05-22 |
| **Drives** | Increment 6.2c (the agent module + `/extract` endpoint + chained ingest). |
| **Roadmap** | [`deployai-source-of-truth-spec.md`](./deployai-source-of-truth-spec.md) §16 — Phase 6. |
| **Builds on** | [`deployment-matrix-model.md`](./deployment-matrix-model.md) — the matrix property graph; and increment 6.2a — the `matrix_proposals` review loop. |

This document is the **decision record** for the matrix extraction agent that produces proposals into the 6.2a review loop. It is increment 6.2b's deliverable: it does not ship code. Increment 6.2c builds the module from it.

---

## 1. Why — the loop in one paragraph

Phase 6.1 lands interactions as canonical events. Phase 6.2a accepts/rejects proposed matrix entities into the matrix, citing the source event. **What's missing is the producer of those proposals** — a Cartographer-style agent that reads an event (plus the engagement's current matrix for context) and emits typed node/edge proposals with rationales. That is 6.2c. 6.2b decides the agent's *shape*: what triggers it, how it talks to the LLM, what it returns, and how it survives failures.

---

## 2. Trigger

**Decision: a per-event `/extract` CP endpoint, chained from `/ingest` by the BFF.**

- `POST /internal/v1/engagements/{id}/extract?event_id=…` — runs extraction on one canonical event, returns the created proposals.
- The web BFF's `/ingest` route, after a successful CP `/ingest`, calls CP `/extract` for the new event. **Best-effort:** extraction failure does **not** fail the ingest (the event is real; the agent is recoverable).
- A separate endpoint also enables: re-extracting a single event on demand, batch tools running over historical events, and a future "Extract" button on the detail page.

Rejected alternatives:
- *Extraction inline inside `/ingest`.* Couples two concerns; ingest gets slow and unreliable; failure becomes ambiguous.
- *Async queue worker.* Right for production, premature for prototype (needs queue + worker infra).

---

## 3. LLM provider injection

The agent depends on the `LLMProvider` protocol in [`packages/llm-provider-py`](../../packages/llm-provider-py/) (`chat_complete` returns `str`; `AnthropicProvider`, `OpenAIProvider`, `create_stub_provider` already exist).

- **Production:** `AnthropicProvider` (per spec §3 — Anthropic is the canonical client).
- **Tests:** `create_stub_provider()` returns deterministic strings — or a per-test `vi.fn`-style mock that returns a known JSON, injected via FastAPI's `app.dependency_overrides`.
- **Injection point:** a CP module-level `get_llm_provider()` factory used as `Depends(get_llm_provider)` in the `/extract` route. Tests override the dependency to swap the stub in.

**Async note:** `chat_complete` is **sync** (uses `httpx` synchronously). To avoid blocking the event loop in async handlers, 6.2c calls it via `await asyncio.to_thread(provider.chat_complete, …)`.

---

## 4. Prompt shape

The agent sends one chat completion per event.

**System prompt** — task contract:

```
You are the Cartographer for DeployAI's deployment matrix.

You read one interaction (a meeting note, email, field note, or manual
import) and propose typed matrix entities that the interaction supports.

Return a JSON array. Each element is one of:

  { "kind": "node",
    "node_type": "stakeholder"|"organization"|"system"|"decision"
                |"risk"|"commitment"|"opportunity",
    "title": string,
    "rationale": string (≤ 200 chars, what in the text supports this) }

  { "kind": "edge",
    "edge_type": "belongs_to"|"owns"|"sponsors"|"blocks"|"affects"
                |"threatens"|"owed_by"|"owed_to"|"depends_on"|"enables",
    "from_title": string (must match an existing matrix node title),
    "to_title": string (must match an existing matrix node title),
    "rationale": string }

Rules:
- Only propose what the text clearly supports. Return [] if nothing extractable.
- Do not duplicate existing matrix nodes — prefer drawing edges to them.
- Output ONLY the JSON array. No prose, no code fences, no commentary.
```

**User prompt** — the event + matrix context:

```
Existing matrix nodes for this engagement:
- <title> (<node_type>)
- ...

Interaction:
- source: <source>
- occurred_at: <iso>
- content: |
    <truncated text — first 8000 chars of the event payload>
```

The `node_type` / `edge_type` catalogues are sourced from the same constants used by the CP API (`_MATRIX_NODE_TYPES`, `_MATRIX_EDGE_TYPES` in `engagements_internal.py`) so the prompt drifts together with the schema.

---

## 5. Response parsing & validation

Per proposal returned by the LLM:

1. **Strict JSON parse.** If the whole response fails to parse, log + return zero proposals. (No retry, no clever extraction; failures are loud and obvious.)
2. **Cap at 20** proposals — defensive; truncate after.
3. **Per-proposal validation:**
   - `kind` ∈ {`"node"`, `"edge"`}.
   - For node: `node_type` ∈ catalog; `title` non-empty.
   - For edge: `edge_type` ∈ catalog; `from_title` and `to_title` both resolve to **existing matrix nodes in this engagement**. If either doesn't resolve, **drop the proposal** (we do not auto-create nodes from titles).
   - `rationale` ≤ 500 chars (truncate).
4. **Persist** valid proposals as `matrix_proposals` rows (status=`pending`) with `source_event_id = event_id`, `payload` shaped ready-to-insert (for edges, `from_node_id`/`to_node_id` resolved from titles).
5. **Skipped proposals are logged**, not surfaced — the agent is best-effort.

---

## 6. Idempotency

**Decision: the `/extract` endpoint is idempotent at the event level.** If `matrix_proposals` already has any rows with `source_event_id = event_id`, the endpoint returns those existing proposals without calling the LLM again.

- Same-event re-extraction is a deliberate operation; the prototype supports it via a `?force=true` query (drops existing proposals for the event, re-runs). 6.2c includes the `force` switch.
- Cost guardrail: re-extraction without `force` is free (no LLM call).

---

## 7. Code location

The agent lives **inside the control plane**:

- `services/control-plane/src/control_plane/agents/matrix_extractor.py` — the pure function: `extract_matrix_proposals(event, existing_nodes, llm) -> list[ProposalDraft]`. No FastAPI / SQLAlchemy here — composable + unit-testable with a fake LLM.
- The `/extract` route handler in `engagements_internal.py` calls `extract_matrix_proposals`, resolves edge titles → node IDs, persists rows.

The cartographer **service** (`services/cartographer/`) stays as-is — it's a separate concern (canonical-memory entity extraction, not engagement matrix). Reusing its prompts is tempting but the output shape and tenant grain differ; cleaner to build a new module than to bend the existing one.

---

## 8. Guardrails

- **Content truncation:** event payload content truncated to 8 000 characters before being sent to the LLM. Log when truncation occurs.
- **Proposal cap:** at most 20 proposals per event (drop the tail).
- **Max output tokens:** 2 000 (passed to `chat_complete`).
- **Temperature:** 0.0 — deterministic for replays + tests.
- **LLM errors caught:** network, auth, rate-limit failures return zero proposals (best-effort); ingest is unaffected.
- **No retries:** if the LLM is failing, the user gets `[]` and a log entry; they can re-trigger from the UI later.

---

## 9. Schema sketch — the `ProposalDraft` shape (6.2c)

Pure Python dataclass-style shape returned by `extract_matrix_proposals`:

```
ProposalDraft (node):
  kind = "node"
  payload = { node_type, title, rationale? }

ProposalDraft (edge, after title→id resolution):
  kind = "edge"
  payload = { edge_type, from_node_id, to_node_id, rationale? }
```

The handler maps each `ProposalDraft` to a `MatrixProposal` row: `proposal_kind = kind`, `payload = payload`, `rationale = payload.rationale`, `source_event_id = event_id`. The rest defaults (status=pending, decided_at=null, …).

---

## 10. Mocking the LLM in tests

- **Unit test for `extract_matrix_proposals`** uses an inline fake LLM that returns a hand-crafted JSON string. Fast, no network, no Docker.
- **Integration test for the `/extract` route** uses `app.dependency_overrides[get_llm_provider] = lambda: <fake>` to swap in a stub provider. Tests cover: end-to-end proposal creation, idempotency on re-run, `force=true` re-extracts, bad JSON returns zero proposals.

---

## 11. Increment plan (the implementation — 6.2c)

| Step | What |
| --- | --- |
| 1 | `control_plane/agents/matrix_extractor.py` — the pure function + ProposalDraft shape. Unit test with a fake LLM. |
| 2 | `get_llm_provider()` factory in CP; AnthropicProvider in prod, env-toggleable to stub in dev. |
| 3 | `POST /internal/v1/engagements/{id}/extract?event_id=…&force=` route in `engagements_internal.py`. Idempotency check; `asyncio.to_thread` wrapper around `chat_complete`. Integration test with dependency override. |
| 4 | Web: `cpExtractMatrixProposals` in `ingest-cp.ts` (or its own `extract-cp.ts`); the BFF `/ingest` route chains `/extract` best-effort after success. Test that ingest still succeeds when extract is mocked to fail. |

---

## 12. Open questions — carried into 6.2c

- **Same-tenant duplicate-node prevention.** The prompt says "do not duplicate existing nodes," but the LLM may still propose `"LiDAR ingest pipeline"` when `"LiDAR ingest"` exists. For 6.2c: rely on the prompt + human review; a similarity check is a refinement.
- **Cost telemetry.** The LLM provider emits usage callbacks (`packages/llm-provider-py/util.py`'s `record_usage`); 6.2c should record per-extract cost on the proposal row or in logs.
- **Re-extract trigger on manual matrix edits.** When the operator adds nodes manually (5.4), the LLM's "existing nodes" context drifts. Out of scope; re-extract any event manually via `?force=true`.
- **Multi-event batching.** A single LLM call over several recent events is cheaper but couples failures. Prototype runs per-event; batch is a later optimization.
