# Agent Kenny v2 — Scope and Phased Build Plan

**Status:** v2 build COMPLETE as of 2026-05-27. Every phase below is shipped on `main`. This document is preserved
as the historical record of *what* was built and *why* in that order. The original scope text is unedited below;
each phase heading is marked with its ship status and merging-PR range.
**Last updated:** 2026-05-27.
**Companion:** [`ethos.md`](./ethos.md) for the architectural decision and inspiration. [`INDEX.md`](./INDEX.md)
for the full Kenny doc map. [`eval.md`](./eval.md) for the Phase 6 harness.
**Owner:** Kenny Geiler.

---

## STATUS — phase ship record

| Phase | Status | Merged PR(s) | Land date |
|---|---|---|---|
| **Phase 0** — AGE + 10x fixtures | shipped | #225, #226, #227 | 2026-05-23 → 2026-05-25 |
| **Phase 0.5** — Compounding synthesis layer | shipped | #228, #229 | 2026-05-25 |
| **Phase 0.6** — Lint worker | shipped | #230 | 2026-05-25 |
| **Phase 1** — 12-tool layer | shipped | #231 | 2026-05-25 |
| **Phase 2** — LangGraph multi-step loop | shipped | #232, #233 (native tool-use follow-up) | 2026-05-25 |
| **Phase 3** — Citation verification + adversarial review | shipped | #234 (+ #236 stub fix) | 2026-05-25 |
| **Phase 4** — MCP inbound server | shipped | #235 | 2026-05-26 |
| **Phase 5** — MCP outbound | shipped (10 PR waves) | see §STATUS-Phase-5 below | 2026-05-26 |
| **Phase 5.5** — pgvector fuzzy fallback | shipped | #248, #249, #250 (Waves A / B / C) | 2026-05-26 |
| **Phase 6** — Eval harness + dashboard | shipped | #251 (Wave B CI), #252 (Wave A harness), #253 (Wave C dashboard) | 2026-05-27 |

**Next phase (not in this document):** cloud deploy on Fly.io + Cloudflare Access.

### STATUS-Phase-5 — wave detail

Phase 5 (MCP outbound) was the largest at 10 PRs across four waves. Wave 1 stood up the schema + external citation
prefixes; Wave 2 built the outbound client, CP routes, rate limits, kill switch; Wave 3 wired the agent loop,
admin UI, connector catalog, and audit / timeline surfacing.

| Wave | Slice | PR |
|---|---|---|
| 1A | `tenant_mcp_configs` schema (migration `0048`) | #237 |
| 1C | External citation prefixes (`[slack:…]`, etc.) | #238 |
| 2D | Outbound MCP client (`mcp_client.py`) | #242 |
| 2E | `tenant_mcp_configs` CP routes | #240 |
| 2F | Kill-switch + rate limit (migration `0049`) | #241 |
| 3G | Agent loop MCP tool merge | #246 |
| 3H | Integrations admin UI | #245 |
| 3I | Outbound MCP audit + timeline surfacing | #247 |
| 3J | Connector catalog + OAuth env wiring (Slack end-to-end; Linear/GDrive/Notion/GitHub `501`) | #244 |
| n/a | Phase 5 MCP outbound threat model (docs) | #239 |

---

## 0. Premise

This plan upgrades Agent Kenny from a single-turn RAG-shaped LLM call into a multi-step, tool-using, citation-verified, MCP-bridged agent. The work is **additive** to the current Postgres + ledger + matrix substrate — no schema breakage, no parallel storage system.

The principles behind every phase are stated in [`ethos.md`](./ethos.md). This document is the *how*.

---

## 1. Scope at a glance

| Phase | Deliverable | Wall time | Risk |
|---|---|---|---|
| **0** | AGE extension + 10x seed fixtures | 1 wk | medium |
| **0.5** | Compounding synthesis layer | 1 wk | low |
| **0.6** | Lint worker | 3–4 d | low |
| **1** | Tool layer (12 tools) | 1 wk | low |
| **2** | LangGraph multi-step loop | 2 wk | high |
| **3** | Citation verification + adversarial review | 1 wk | medium |
| **4** | MCP inbound server | 1 wk | medium |
| **5** | MCP outbound (tenant-enabled integrations) | 1–2 wk | high |
| **5.5** | pgvector embeddings (fuzzy fallback) | 3–4 d | low |
| **6** | Eval harness + hallucination dashboard | 1 wk | low |

**Total: ~9–11 weeks.** Each phase ships independently; the first shippable v2 milestone is Phases 0–0.6 + 1 + 3, around week 5.

---

## 2. Phase 0 — Foundations (1 wk) — Shipped (PRs #225, #226, #227)

### 2.1 Apache AGE extension
- **Migration:** `services/control-plane/alembic/versions/0043_apache_age.py` — `CREATE EXTENSION age; SELECT create_graph('deployai_matrix');`
- **Triggers:** `services/control-plane/src/control_plane/domain/canonical_memory/age_sync.py` — pg triggers that mirror `matrix_nodes` / `matrix_edges` writes into the AGE graph view. Tenant + engagement properties on every vertex/edge for filtered traversal.
- **Cypher helper module:** `services/control-plane/src/control_plane/agents/tools/graph.py` — thin wrapper around `psycopg.execute("SELECT * FROM cypher(...)")`.
- **Decision deferral:** ship the install + triggers in Phase 0; defer using AGE for queries until Phase 1 tool layer needs it. If recursive CTEs prove sufficient in Phase 1, AGE installation is sunk cost (small).

### 2.2 10x seed fixtures
- **BlueState-XL:** 5-year single-engagement fixture. ~70 stakeholders, ~200 decisions, ~130 risks, ~2.5k ledger events, ~600 edges, 1825-day snapshot backfill.
  - `services/control-plane/src/control_plane/scenarios/bluestate_xl/builder.py`
  - `services/control-plane/src/control_plane/scenarios/bluestate_xl/events.py`
  - `services/control-plane/src/control_plane/scenarios/bluestate_xl/runner.py`
- **DeployAI-Portfolio:** 5 sibling engagements × 26 weeks each. Tests cross-engagement isolation.
  - `services/control-plane/src/control_plane/scenarios/portfolio/`
- **CP routes:**
  - `POST /internal/v1/admin/seed-scenarios/bluestate-xl`
  - `POST /internal/v1/admin/seed-scenarios/portfolio`
- **Onboarding wizard cards:** extend `apps/web/src/components/onboarding/OnboardingWizard.client.tsx` with two new picker buttons (alongside existing BlueState card).
- **Tests:** `services/control-plane/tests/integration/test_seed_scenarios_xl.py` + `test_seed_scenarios_portfolio.py`. Confirm row counts, tenant isolation, snapshot counts, lint pass returns clean state initially.

### 2.3 Exit criteria
- AGE extension installed; sample Cypher query returns expected results.
- BlueState-XL wizard button seeds 5-year fixture in <60s.
- Portfolio wizard button seeds 5 engagements; cross-engagement queries return zero leakage.
- All existing tests still pass.

---

## 3. Phase 0.5 — Compounding synthesis layer (1 wk) — Shipped (PRs #228, #229)

The substrate already has `matrix_insights` and `temporal_insights`. Today they are mostly one-shot. v2 makes synthesis a continuously-refreshed asset.

### 3.1 Schema extensions
- **Migration `0044_synthesis_compounding.py`:**
  - Add `matrix_insights.source_event_ids` (uuid[]) if not present
  - Add `matrix_insights.last_refreshed_at` (timestamptz)
  - Add `matrix_insights.stale` (bool default false)
  - Add CHECK constraint that `source_event_ids` is non-empty when `agent='oracle'` or `agent='kenny'`

### 3.2 Synthesis workers
- **`services/control-plane/src/control_plane/workers/synthesizer.py`** — async worker triggered by:
  - New `proposal_accepted` event for a `decision` node → produce/refresh `decision_provenance_summary` insight
  - New `insight_opened` event with severity ≥ high → produce/refresh `risk_explainer` insight that summarizes evidence
  - New `member_added` for a stakeholder → produce/refresh `stakeholder_brief` in that node's `attributes.description`
- Each writes a typed `matrix_insights` row or updates the target node's `attributes.description` with per-claim citations.
- Adversarial-review-light: synthesizer calls the LLM with a "list claims, cite each" structured-output prompt; output is validated before persist.

### 3.3 Per-claim provenance discipline
- **New helper `claim_cite.py`** validates that every paragraph in a synthesized description carries at least one `[event:UUID]` or `[node:UUID]` cite, all of which resolve to rows in the same engagement + tenant.
- Synthesizer rejects + retries (once) if validation fails. Persistent failure emits `synthesis_validation_failed` ledger event.

### 3.4 Exit criteria
- Seeding BlueState-XL produces ≥10 compounding `matrix_insights` rows beyond what the deterministic analyzers emit.
- Every synthesized row passes citation validation (per-claim, in-engagement).
- A re-seed (force=true) refreshes existing synthesis without duplication.

---

## 4. Phase 0.6 — Lint worker (3–4 d) — Shipped (PR #230)

### 4.1 Scope
- **`services/control-plane/src/control_plane/workers/wiki_lint.py`** — periodic + event-triggered.
- **Checks:**
  - *Contradiction:* two `matrix_insights` rows or two decision narratives that disagree on the same node within a 14-day window → emit `lint_contradiction_flagged` with both insight ids.
  - *Stale claim:* `matrix_insights` with `last_refreshed_at` older than 30 days *and* upstream source events have new descendants → mark `stale=true` + emit `lint_stale_flagged`.
  - *Orphan synthesis:* `matrix_insights` row whose `source_event_ids` no longer exist (events deleted) → mark `orphan=true`.
  - *Missing cite:* `matrix_nodes.attributes.description` paragraph without any `[event:…]` or `[node:…]` cite → emit `lint_missing_cite_flagged`.
  - *Broken cite:* citation UUID in any prose field that doesn't resolve in this tenant + engagement → emit `lint_broken_cite_flagged`.

### 4.2 Triggers
- After every `proposal_accepted`, `matrix_node_updated`, `insight_opened`, `insight_closed` ledger event → enqueue lint for affected rows.
- Nightly cron at 04:00 UTC for the safety-net pass.

### 4.3 Surfaces
- New flagged events show up in the existing temporal-insight surface (Phase F).
- New table `lint_flags` (id, kind, target_kind, target_id, flagged_at, resolved_at, tenant_id, engagement_id) for the hallucination dashboard.

### 4.4 Exit criteria
- Seeding BlueState-XL produces a lint pass with <5 flags (the deliberate noise events in the fixture).
- Manually mutating a synthesized row to break a citation triggers `lint_broken_cite_flagged` within 30s.

---

## 5. Phase 1 — Tool layer (1 wk) — Shipped (PR #231)

12 tools, pure functions, all tenant + engagement scoped. Each returns a structured `ToolResult` with rows + citations + truncation flag.

### 5.1 Tools

| Tool | Purpose | Implementation hint |
|---|---|---|
| `query_ledger` | Paginated ledger search by source_kind / date / actor / text | SQLAlchemy over `ledger_events` with affects-join when needed |
| `walk_chain` | Causal chain walk from an event, upstream / downstream / both | Existing `get_ledger_event_chain` BFS, exposed as a tool |
| `get_matrix_node` | Full node row + attributes + 1-hop neighbors | Single SQL with edge join |
| `get_matrix_neighbors` | k-hop neighbors filtered by edge_type | AGE Cypher if installed, recursive CTE fallback |
| `get_matrix_subgraph` | Bounded subgraph by filter (node_types, edge_types, since) | AGE Cypher preferred |
| `read_synthesis` | Read all `matrix_insights` for a node/engagement | Plain SELECT |
| `get_decision_history` | Decisions ordered with their proposal chain | SQL + small join |
| `get_open_risks` | Filtered open risks with citations | SELECT + filter |
| `get_engagement_summary` | Aggregate snapshot of engagement state | Read materialized view if available, else compute |
| `vector_search` | (Phase 5.5) fuzzy semantic recall | pgvector cosine HNSW |
| `keyword_search` | BM25-ish over event summaries + node attributes | `pg_trgm` + `tsvector` |
| `propose_action` | **Only write tool.** Inserts into `strategist_action_queue_items` for human review. | INSERT + ledger emit |

### 5.2 Common shape

```python
@dataclass(frozen=True)
class Citation:
    kind: Literal["event", "node", "insight", "turn"]
    id: uuid.UUID

@dataclass(frozen=True)
class ToolResult:
    name: str
    rows: list[dict[str, Any]]
    citations: list[Citation]
    truncated: bool
    next_cursor: str | None

class Tool(Protocol):
    name: str
    input_schema: dict[str, Any]  # JSON schema for the Anthropic tool_use payload
    async def __call__(self, session: AsyncSession, *, tenant_id, engagement_id, **kwargs) -> ToolResult: ...
```

### 5.3 Files
```
services/control-plane/src/control_plane/agents/tools/
├── __init__.py        # registry + JSON schema export
├── ledger.py          # query_ledger, walk_chain
├── matrix.py          # get_matrix_node, _neighbors, _subgraph
├── synthesis.py       # read_synthesis
├── analysis.py        # get_decision_history, get_open_risks, get_engagement_summary
├── search.py          # vector_search (Phase 5.5), keyword_search
├── escalate.py        # propose_action
└── audit.py           # invocation-emit helper used by all tools
```

### 5.4 Auditability
- Every tool call begins with `emit_ledger_event(source_kind='agent_tool_invocation', ...)` recording the tool name, redacted input hash, caller turn_id, and tenant + engagement scope.
- Result row counts + duration_ms are appended to the ledger event detail when the tool returns.

### 5.5 Exit criteria
- All 12 tools have green unit tests asserting tenant isolation, citation correctness, and pagination behavior.
- `agent_tool_invocation` ledger emits are visible in the engagement timeline UI.

---

## 6. Phase 2 — LangGraph multi-step loop (2 wk) — Shipped (PRs #232, #233)

### 6.1 State machine

```
[entry]
   ↓
[retrieve_initial_context]   ← matrix summary + open insights + recent ledger (small, dense)
   ↓
[call_llm_with_tools]        ← Anthropic messages API with tools[]
   ↓
[has_tool_calls?] —— yes ──→ [dispatch_tools] ──→ [append_results] ─┐
   ↓ no                                                              │
[extract_citations]                                                  │
   ↓                                                                 │
[verify_citations]                                                   │
   ↓                                                                 │
[unverified > 0?] —— yes ──→ [revise_once] ──→ [verify_again]        │
   ↓ no                                                              │
[adversarial_review]                                                 │
   ↓                                                                 │
[persist_turn + emit_audit_trace]                                    │
   ↓                                                                 │
[stream_done_frame] ←───────────────────────────────────────────────┘
```

### 6.2 Budgets
- Max **8** tool calls per turn (tenant-configurable).
- Max **2** revision attempts.
- Hard timeout **60s** per turn.
- Per-tenant daily LLM token cap (existing `check_and_charge`, extended to count tool-call tokens).

### 6.3 Streaming contract (SSE upgrade)
```
event: thinking
data: {"content":"I need to check the decision history first."}

event: tool_call
data: {"name":"query_ledger","input":{...}}

event: tool_result
data: {"name":"query_ledger","row_count":12,"truncated":false}

event: delta
data: {"content":"Two concerns were raised pre-approval."}

event: citation_verified
data: {"kind":"event","id":"abc..."}

event: done
data: {"turn_id":"...","tokens":1240,"tool_calls":2,"revision_attempts":0}
```

The web client renders intermediate `thinking` + `tool_call` chips above the streaming reply for visible reasoning. Failed citations emit `citation_unverified` events.

### 6.4 Files
```
services/control-plane/src/control_plane/agents/agent_kenny/
├── __init__.py
├── graph.py           # LangGraph StateGraph definition
├── nodes/
│   ├── retrieve.py
│   ├── llm_call.py
│   ├── tool_dispatch.py
│   ├── citations.py
│   ├── revise.py
│   ├── adversarial.py
│   └── persist.py
├── stream.py          # SSE frame formatters
├── budget.py
└── types.py           # AgentState dataclass + Pydantic models
```

### 6.5 Cutover
- Existing `OracleChatService` stays alive as a thin compatibility shim for one release.
- New `KennyAgentService` runs the LangGraph loop.
- Feature flag `DEPLOYAI_AGENT_KENNY_V2_ENABLED` per tenant. Default off; flip on per pilot tenant.

### 6.6 Exit criteria
- Golden-question set (Phase 6) achieves ≥80% pass rate against BlueState-XL.
- Mean latency <8s for 90th percentile question.
- No cross-tenant leakage observable in cross-tenant-fuzz CI.

---

## 7. Phase 3 — Citation verification + adversarial review (1 wk) — Shipped (PR #234, stub fix #236)

### 7.1 Citation verification

```python
CITATION_RE = re.compile(
    r"\[(event|node|insight|turn):([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})\]"
)
```

- Parse during streaming. As deltas arrive, queue matches for async DB lookup. Verifier runs in parallel with the stream.
- Each citation's existence is checked against the matching table, **scoped to current tenant + engagement**.
- Outcome per citation: `verified`, `cross_engagement_leak` (exists but in another engagement — security event), `not_found` (hallucinated), or `external` (slack/linear/gdrive — trusted upstream, recorded but not DB-checked).
- `cross_engagement_leak` is a hard incident: reply is REJECTED, security ledger event emitted, response is replaced with "I'm unable to answer that question."

### 7.2 Revision loop
- If `not_found` citations exist after streaming complete:
  1. Feed reply + the list of bad citations back to the model with a corrective prompt.
  2. Accept the revision if it removes the bad citations OR replaces them with valid ones.
  3. Max 2 revision attempts.
- If still hallucinating after revisions: strip the bad citations from the rendered reply, add an inline warning, emit `agent_hallucination_unresolved` ledger event.

### 7.3 Adversarial review
- After citations pass, run a second LLM call (Haiku 4.5) with this system prompt:
  > "You are an auditor. Read this reply and the evidence provided. List concerns: unstated assumptions, claims not supported by evidence, overconfident generalizations. Be terse."
- Output is parsed into structured concerns.
- If concerns flagged AND any citation also failed → trigger revision.
- If concerns flagged alone → emit `agent_audit_concern` ledger event for human review; ship reply unchanged.

### 7.4 Schema
- **Migration `0045_agent_audit_traces.py`:** new table `agent_audit_traces` (id, turn_id, total_citations, verified_count, unverified_count, cross_engagement_count, revision_attempts, adversarial_concerns_count, final_text, created_at, tenant_id, engagement_id).

### 7.5 Files
```
services/control-plane/src/control_plane/agents/agent_kenny/nodes/citations.py
services/control-plane/src/control_plane/agents/agent_kenny/nodes/adversarial.py
services/control-plane/alembic/versions/0045_agent_audit_traces.py
apps/web/src/components/settings/HallucinationRateCard.client.tsx
```

### 7.6 Exit criteria
- Synthetic test: prompt Kenny with a question whose answer requires citing event X; manually delete X from the DB; reply should be revised or warn, not hallucinate.
- Cross-engagement test: ask Kenny in engagement A about engagement B; reply should be rejected via `cross_engagement_leak` path.
- Adversarial reviewer catches a deliberate overreach in eval harness; flag is recorded.

---

## 8. Phase 4 — MCP inbound server (1 wk) — Shipped (PR #235)

Standalone uvicorn service exposing DeployAI as an MCP server. Advisors run their own Claude desktop (or any MCP client) with this configured → they query the matrix directly without going through DeployAI's UI.

### 8.1 Service
- **`services/mcp-server/`** — separate compose container, port 3030.

### 8.2 Resources (read-only)
```
engagement://{id}            → engagement summary + members + phase
node://{id}                  → matrix node full payload
event://{id}                 → ledger event + chain
chain://{event_id}           → causal walk
search/event?q=...           → vector + keyword search results
search/node?q=...            → matrix node search
```

### 8.3 Tools (read-only on inbound)
The same Phase 1 read tools exposed via MCP. `propose_action` is **not** exposed to inbound.

### 8.4 Auth
- Bearer token in `Authorization` header.
- New table `tenant_api_keys` (id, tenant_id, name, hashed_secret, scopes, last_used_at, created_at, revoked_at). Scope = one engagement, read-only.
- Tenant admin mints keys from settings UI; raw key shown once.

### 8.5 Files
```
services/mcp-server/
├── pyproject.toml
├── Dockerfile
├── src/mcp_server/
│   ├── main.py        # MCP protocol handler (HTTP/SSE transport)
│   ├── resources.py
│   ├── tools.py       # imports from control_plane.agents.tools
│   ├── auth.py
│   └── audit.py       # every external call emits a ledger event in CP
infra/compose/docker-compose.yml  (+ mcp-server service)
apps/web/src/app/(strategist)/settings/api-keys/page.tsx
services/control-plane/alembic/versions/0046_tenant_api_keys.py
```

### 8.6 Exit criteria
- Advisor's Claude desktop, configured with one of these tokens, can query BlueState-XL's matrix and get cited responses.
- Token revocation is immediate (next call → 401).
- Cross-engagement attempt with a single-engagement-scoped token → 403.

---

## 9. Phase 5 — MCP outbound (1–2 wk) — Shipped (10 PRs across 4 waves; see STATUS-Phase-5 table above)

Agent Kenny calls **external** MCP servers when reasoning needs data DeployAI doesn't own.

### 9.1 Tenant configuration
- **Migration `0047_tenant_mcp_configs.py`:** new table `tenant_mcp_configs` (id, tenant_id, name, transport, endpoint, encrypted_auth_token, enabled, allowed_tools, created_at).
- Tenant admin enables MCPs from a curated catalog. v1 catalog:
  - Slack (`slack-mcp`)
  - Linear (`linear-mcp`)
  - GDrive (`gdrive-mcp`)
  - Notion (`notion-mcp`)
  - GitHub (`github-mcp`)
- OAuth flow stored encrypted using existing tenant-DEK pattern. Refresh handled by CP cron.

### 9.2 Tool merge
- At agent loop start: load enabled MCPs for this tenant → fetch each MCP's tool list → merge into Kenny's tool registry, namespaced (`slack.search_messages`, `linear.list_issues`, …).
- Allow-list per MCP: `allowed_tools` column restricts which of the MCP's tools Kenny may invoke.

### 9.3 External citations
- Replies citing external sources use kinded prefixes: `[slack:msg-uuid]`, `[linear:issue-id]`, `[gdrive:file-id]`.
- Citation verifier recognizes these as `external`. Recorded in audit ledger but not DB-checked (trust upstream).

### 9.4 Security review checklist (mandatory before ship)
- OAuth tokens at rest: encrypted with tenant DEK.
- OAuth tokens in transit: TLS-only.
- Allow-list enforced server-side, not just in UI.
- Per-tool rate limits to prevent runaway external calls.
- Audit ledger captures every external call with redacted input.
- Disable-all-external switch in admin UI for incident response.

### 9.5 Files
```
services/control-plane/src/control_plane/agents/agent_kenny/mcp_client.py
services/control-plane/src/control_plane/agents/agent_kenny/external_citations.py
services/control-plane/alembic/versions/0047_tenant_mcp_configs.py
apps/web/src/app/(strategist)/settings/integrations/page.tsx
docs/security/mcp-outbound-threat-model.md
```

### 9.6 Exit criteria
- Enabling Slack MCP for a tenant + asking Kenny "what did the customer say in #bluestate this week" returns a cited reply pulling from both ledger and Slack.
- Disable-all switch immediately revokes Kenny's external tool access for that tenant.
- Security review sign-off on the threat-model doc.

---

## 10. Phase 5.5 — pgvector fuzzy fallback (3–4 d) — Shipped (PRs #248, #249, #250)

Comes *after* MCP outbound because at our scale Karpathy's argument (index + curated synthesis beats embeddings at moderate scale) holds. We add vector search as a **fallback** for fuzzy recall, not the hot path.

### 10.1 Migration
- **`0048_pgvector_embeddings.py`:**
  - Add `embedding vector(1024)` column on `ledger_events`, `matrix_nodes`, `oracle_chat_turns`, `matrix_insights`.
  - HNSW index per column.
- New table `embedding_jobs` (id, source_table, source_id, status, attempts, created_at).

### 10.2 Worker
- **`services/control-plane/src/control_plane/workers/embedder.py`** — polls embedding queue, batches up to 50 per Voyage-3 call, writes back.
- Triggered on row insert/update for the four embedded tables.

### 10.3 Tool
- `vector_search` (defined in Phase 1 placeholder) now becomes operational. Returns top-N by cosine similarity, tenant + engagement scoped.

### 10.4 Exit criteria
- Embedding backlog drains within 30s of a fresh BlueState-XL seed.
- `vector_search("active directory concerns")` returns the W19–W21 narrative events in BlueState-XL.

---

## 11. Phase 6 — Eval harness + dashboard (1 wk) — Shipped (PRs #251 Wave B CI, #252 Wave A harness, #253 Wave C dashboard)

### 11.1 Golden questions
- 30 hand-curated questions targeting BlueState-XL. Categories:
  - Direct lookup ("who is the executive sponsor?")
  - Causal chain ("trace decision X to its origin")
  - Negative answers ("I don't know" — questions whose answer is *not* in the data)
  - Cross-engagement protection ("what about BlueState-Y?" — answer must refuse)
  - Multi-hop ("what risks are upstream of the SSO migration that mention legal?")
- File: `services/control-plane/tests/golden/agent_kenny/questions.yaml`

### 11.2 Eval runner
- `services/control-plane/tests/golden/agent_kenny/runner.py`
- Spawns Kenny against a freshly-seeded BlueState-XL instance per question.
- Records per-turn metrics:
  - Wall clock latency
  - Tool calls
  - Citations total / verified / unverified
  - Revision attempts
  - Adversarial concerns
  - "I don't know" usage rate
  - Semantic match against expected answer (LLM judge)
- Outputs JSON report; CI uploads as workflow artifact.

### 11.3 CI integration
- Nightly: random 5-question sample. Hard fail CI if any cross-engagement leak.
- Weekly: full 30-question set.
- File: `.github/workflows/agent-kenny-eval.yml`

### 11.4 Dashboard
- New admin page `apps/web/src/app/(strategist)/admin/agent-kenny-dashboard/page.tsx`
- Surfaces:
  - Hallucination rate (unverified / total citations) — 7d trend
  - Tool-call distribution (which tools fire most)
  - p50 / p95 / p99 latency
  - "I don't know" rate
  - Lint flag counts by kind
  - Top 10 most-cited events / nodes
  - Adversarial concerns flagged

### 11.5 Exit criteria
- Eval runs in CI nightly + weekly without manual intervention.
- Dashboard renders with real data from BlueState-XL.
- Documented baseline numbers (hallucination rate, latency, etc.) for v2.0 ship.

---

## 12. Order of execution

```
[Phase 0]──[Phase 0.5]──[Phase 0.6]──[Phase 1]──┬──[Phase 2]──[Phase 3]──[Phase 4]──[Phase 5]──┐
                                                │                                              │
                                                └──[Phase 5.5]─────────────────────────────────┴──[Phase 6]
```

Phases 0 / 0.5 / 0.6 are sequential because each builds on the previous (AGE for tools → synthesis for Kenny → lint for synthesis). Phase 1 begins as soon as 0.6 completes. Phase 5.5 can start in parallel with Phase 4 if engineering capacity allows.

---

## 13. Risks and mitigations

| Risk | Mitigation |
|---|---|
| LangGraph state-machine complexity blows the timeline | Time-box Phase 2 to 2 weeks; if not converging, fall back to a hand-rolled state machine (~300 LOC, no framework dep). |
| Adversarial reviewer too noisy → blocks valid replies | Start in shadow mode (concerns logged but reply ships unchanged); promote to blocking only after false-positive rate <5%. |
| AGE install fails on pg image (pgvector base) | Test against the existing `deployai/postgres` image early; fall back to recursive CTEs (no perf cliff at our scale). |
| MCP outbound OAuth token leak | Strict audit on Phase 5 PR before merge; threat model doc reviewed. Disable-all switch. |
| 10x seed exposes pre-existing perf bugs | Acceptable — surface them in Phase 0 testing, fix or scope-cut before Phase 1. |

---

## 14. What this plan does **not** include

- Multi-engagement portfolio reasoning by Kenny. v2 is one-engagement-at-a-time.
- Writing to the matrix from Kenny. Only `propose_action` (which inserts into a human-review queue).
- Vector search as primary retrieval. Stays fallback.
- Markdown filesystem projection. The DB tables are the wiki.
- Real-time meeting transcript ingest. Kenny works with what's already in the ledger.
- A "live tail" mode where Kenny ambient-monitors incoming events.

These are explicit non-goals for v2. If they become product priorities, scope a v3.

---

## 15. Open decisions (carried from ethos.md §7)

- Embedding model: Voyage-3 (Anthropic) vs `text-embedding-3-large` (OpenAI). Lean Voyage.
- AGE vs recursive CTEs: decide end of Phase 0.
- Adversarial reviewer: Haiku 4.5 vs Sonnet 4.6. Start Haiku, escalate if FN rate >5%.
- Lint cadence: event-triggered + nightly safety net. Default to this.

---

## 16. Where this came from

- Karpathy's *LLM Wiki* gist (https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f) — the compounding-synthesis argument.
- Synthadoc commenter — claim-level provenance pattern.
- Anthropic's MCP — agent tooling protocol.
- LangGraph (https://langchain-ai.github.io/langgraph/) — state machine for the multi-step loop.
- Our own ledger + matrix substrate — the unexpected gift of having built the right primitives early.

For the *why*, read [`ethos.md`](./ethos.md). This document is the *how*.
