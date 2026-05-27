# Agent Kenny — documentation hub

**Status:** v2 build COMPLETE as of 2026-05-27. Phases 0 through 6 all shipped on `main`.

Agent Kenny is DeployAI's chat surface — a multi-step LangGraph agent that answers questions about a single
customer deployment with cited, grounded responses. He runs against one engagement at a time, never crosses
tenants, and never fabricates citations. Read [`ethos.md`](./ethos.md) for *why* the substrate is shaped this way;
[`scope-v2.md`](./scope-v2.md) for the phase-by-phase ship record; [`eval.md`](./eval.md) for the harness that
gates CI.

---

## Map of every Kenny-related doc

### Start here

| Doc | One-line summary | When to read |
|---|---|---|
| [`ethos.md`](./ethos.md) | Architectural rationale: ledger is the wiki, Kenny is its disciplined librarian, every claim cites its source, every synthesis compounds. The load-bearing decision doc. | First. Read in full before changing the agent or its tools. |
| [`scope-v2.md`](./scope-v2.md) | Phase-by-phase build record — Phases 0 through 6, with merged-PR pointers and a Phase 5 wave table. Now historical, kept verbatim. | When you need to understand *why something was built in that order* or trace a feature back to its merging PR. |
| [`eval.md`](./eval.md) | The 30-golden-question eval harness against BlueState-XL: what it measures, CI cadence, how to run locally, how to interpret a `cross_engagement_leak` failure. | When a CI eval fails, when you're adding a new golden question, or when adjusting agent behavior. |

### Adjacent design + security docs (not in `agent-kenny/` but Kenny-critical)

| Doc | One-line summary | When to read |
|---|---|---|
| [`../design/timeline-ledger.md`](../design/timeline-ledger.md) | The core data model: `ledger_events`, `ledger_event_causes`, `ledger_event_affects`, `matrix_snapshots`, `temporal_insights`. The substrate Kenny reads. | Before adding a new Kenny tool, a new analyzer, or anything that emits ledger events. |
| [`../contracts/citation-envelope.md`](../contracts/citation-envelope.md) | The citation envelope contract (`[event:UUID]`, `[node:UUID]`, etc.). Phase 5's `<external_data source="…">…</external_data>` prompt-injection wrapping pattern lives in the agent loop code. | Before touching citation extraction, verification, or external-result handling. |
| [`../security/mcp-outbound-threat-model.md`](../security/mcp-outbound-threat-model.md) | Phase 5 STRIDE threat model + §9.4 mandatory-checklist mapping. The "what can a poisoned MCP do to us, and what stops it" doc. | Before any change to `mcp_client.py`, the connector catalog, the kill switch, or the rate limiter. |
| [`../security/tenant-isolation.md`](../security/tenant-isolation.md) | The three-layer tenant isolation discipline (RLS + `TenantScopedSession` + cross-tenant fuzz). | When you suspect a leak, when reviewing a new tool, or when the cross-tenant fuzz CI fires. |
| [`../security/cross-tenant-fuzz.md`](../security/cross-tenant-fuzz.md) | The CI fuzz harness that pins tenant isolation. Hooked into every Kenny-touching CI run. | When extending the fuzz target list (e.g. adding a new table to be probed cross-tenant). |
| [`../design/post-f-polish.md`](../design/post-f-polish.md) | Phase G design record — Agent Kenny chat panel, UX bundles G0–G4. Pre-v2; v2 supersedes the agent design but the UX surface decisions stand. | If you're touching the chat panel UI or the Phase G insight-grouping / per-section filters. |

### Code pointers (so you don't have to grep)

| Concern | Path |
|---|---|
| LangGraph state machine | `services/control-plane/src/control_plane/agents/agent_kenny/graph.py` |
| Per-node logic (retrieve, llm_call, tool_dispatch, citations, revise, adversarial, persist) | `services/control-plane/src/control_plane/agents/agent_kenny/nodes/` |
| Service entrypoint | `services/control-plane/src/control_plane/agents/agent_kenny/service.py` |
| Streaming (SSE frames) | `services/control-plane/src/control_plane/agents/agent_kenny/stream.py` |
| Budget caps (tokens, tool calls, revisions, timeout) | `services/control-plane/src/control_plane/agents/agent_kenny/budget.py` |
| 12 internal tools + registry | `services/control-plane/src/control_plane/agents/tools/` |
| Outbound MCP client + connectors + kill switch + rate limit | `services/control-plane/src/control_plane/agents/agent_kenny/mcp_*.py` |
| Synthesizer worker | `services/control-plane/src/control_plane/workers/synthesizer.py` |
| Lint worker | `services/control-plane/src/control_plane/workers/wiki_lint.py` |
| Voyage-3 embedder worker | `services/control-plane/src/control_plane/workers/embedder.py` |
| Inbound MCP server | `services/mcp-server/` |
| Golden questions | `services/control-plane/tests/golden/agent_kenny/questions.yaml` |
| Eval runner | `services/control-plane/tests/golden/agent_kenny/runner.py` |
| Eval CI workflow | `.github/workflows/agent-kenny-eval.yml` |
| Admin dashboard | `apps/web/src/app/(strategist)/admin/agent-kenny-dashboard/` |
| BlueState-XL fixture (5y, ~2.5k events) | `services/control-plane/src/control_plane/scenarios/bluestate_xl/` |
| Portfolio fixture (5 engagements × 26w, isolation stress) | `services/control-plane/src/control_plane/scenarios/portfolio/` |

### Migrations that matter

| Migration | What it landed |
|---|---|
| `0042_apache_age.py` | Apache AGE extension + matrix-write mirroring triggers |
| `0043_synthesis_compounding.py` | `matrix_insights.source_event_ids`, `last_refreshed_at`, `stale` |
| `0044_lint_flags.py` | `lint_flags` table for contradiction / stale / orphan / missing-cite / broken-cite |
| `0045_agent_audit_traces.py` | Per-turn audit trace rows (citations, revisions, adversarial concerns) |
| `0046_phase3_audit_traces_extend.py` | Phase 3 extension fields |
| `0047_tenant_api_keys.py` | Inbound MCP server's tenant API keys |
| `0048_tenant_mcp_configs.py` | Outbound MCP connector configs + encrypted OAuth tokens |
| `0049_mcp_outbound_kill_switch.py` | `app_tenants.mcp_outbound_disabled` boolean (incident-response switch) |
| `0050_pgvector_embeddings.py` | `vector(1024)` columns + HNSW indexes + `embedding_jobs` queue + triggers |

---

## Operational pointers

| Need | Where |
|---|---|
| Run the agent locally | `make dev` + `make seed-scenario-bluestate` → open the chat panel on any engagement detail page |
| Run the larger fixture | Onboarding wizard → "BlueState-XL" button (or the equivalent `POST /internal/v1/admin/seed-scenarios/bluestate-xl`) |
| Verify tenant isolation | Onboarding wizard → "DeployAI Portfolio" button → run the cross-tenant fuzz suite (`uv run pytest tests/fuzz`) |
| Run the eval locally | See [`eval.md`](./eval.md) §Running locally |
| See the dashboard | `/admin/agent-kenny-dashboard` (after `make dev`) |
| Enable an outbound MCP for a tenant | `/admin/integrations` — Slack OAuth wired; Linear/GDrive/Notion/GitHub return `501` for now |
| Incident response: kill all outbound MCPs for a tenant | `/admin/integrations` → kill-switch toggle (sets `app_tenants.mcp_outbound_disabled = true`; per-call short-circuit) |
| Mint a tenant API key for the inbound MCP server | `/admin/api-keys` |

---

## What's **not** here

Things deliberately out of scope for v2 (recorded in `scope-v2.md` §14):

- Multi-engagement portfolio reasoning by Kenny (one engagement at a time).
- Writing to the matrix from Kenny (only `propose_action`, which queues for human review).
- Vector search as primary retrieval (stays fallback; curated synthesis is the hot path).
- Markdown filesystem projection (the DB tables *are* the wiki).
- Real-time meeting transcript ingest (Kenny reads what's already in the ledger).
- Live-tail ambient monitoring.

If a future product priority needs any of these, scope a v3.
