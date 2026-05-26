# Agent Kenny — Ethos and Architectural Decision

**Status:** Authoritative for v2 design. Last updated 2026-05-26.
**Audience:** Engineers building on the agent layer, advisors evaluating the architecture, future maintainers.
**Companion:** [`scope-v2.md`](./scope-v2.md) for the phased build plan.

---

## 1. What Agent Kenny is

Agent Kenny is DeployAI's chat surface — the way strategists ask questions about a long-cycle customer deployment and get cited, grounded answers. He runs against a single engagement at a time, never crosses tenants, and never fabricates citations.

He is **not** a general-purpose assistant. He is the read interface to one customer's audited deployment memory.

---

## 2. The decision

> **Treat the DeployAI substrate as a compounding curated knowledge artifact, not as a raw store to be re-synthesized on every query.**

The default reflex when building an AI feature on a database is *retrieve-each-query RAG*: fetch raw rows, format into a prompt, ask the model, throw the synthesis away. We are explicitly **not** doing that.

Instead, every Agent Kenny interaction does two things in tandem:

1. **Consume the curated substrate** — matrix nodes, ledger events, and analyzer-produced insights that *already represent synthesis the system has done before*. These are the system's accumulated understanding of the engagement.
2. **Compound it** — when Kenny produces a new synthesis worth keeping (a decision-provenance narrative, a multi-event causal summary), it persists back into the substrate as a typed insight or as enriched node attributes. Future turns start from there, not from scratch.

The retrieval engine becomes a navigator over curated views. Re-synthesis from raw events is a fallback path, not the hot path.

---

## 3. Inspirations and what we adopted from each

### 3.1 Andrej Karpathy — *LLM Wiki* gist
> https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f

**Core argument we adopt:** retrieval-at-query-time is wasteful when the same synthesis is recomputed across turns. Better: maintain a persistent compounding artifact that the LLM curates over time, with claim-level provenance and periodic lint passes.

**What we adopted:**

- **Compounding synthesis over re-synthesis.** Insights once produced are persisted as `matrix_insights` rows with citations. Kenny reads them as primary context, not the raw 30-day ledger window.
- **Claim-level provenance.** Every claim inside a node's `attributes.description` carries an inline citation (`[event:UUID]` or `[node:UUID]`). Not just "this node was created by event X" — every *sentence* of curated prose ties back to a source.
- **Lint pass.** A background worker that scans curated content for contradictions, stale claims, orphan references, and missing links. It does not modify content; it *flags* via ledger events that strategists or Kenny himself can resolve.
- **Index over embeddings at moderate scale.** Karpathy's empirical observation that index-based retrieval beats embedding search up to ~1000 sources holds in our scale (BlueState seed = 7 stakeholders, 20 decisions, 13 risks, 249 ledger events; the extended XL fixture is ~10x). Vector search stays in the plan as a Phase 5 fallback for fuzzy recall, not as a Phase 0 critical dependency.

**What we deliberately rejected from his pattern:**

- **Parallel markdown filesystem.** Storing curated prose in `engagement_wikis/<id>/*.md` next to Postgres would introduce a second source of truth, a sync problem, and a multi-tenant filesystem attack surface for zero new value. The pg tables we already have are the wiki. Markdown is at most an *export* projection generated on demand.
- **Obsidian as the editor.** Karpathy's pattern assumes a single human curator browsing markdown. DeployAI is multi-user, multi-tenant, web-UI-driven. The product *is* the wiki view; we don't expose markdown editing.
- **Slow-change assumption.** Karpathy's pattern works best where source material changes weekly. Deployment data changes hourly. Lint and synthesis must run on event-driven triggers, not nightly cron alone.

### 3.2 Synthadoc — claim-level provenance pattern (from gist comments)

The Synthadoc commenter argued that the unit of trust in an LLM-curated document should be the *paragraph*, not the *document*: every paragraph traces to source lines via a citation marker. We adopt this: every prose claim in `matrix_nodes.attributes.description` carries at least one `[event:…]` or `[node:…]` cite. The lint pass enforces this.

### 3.3 Adversarial review pattern (also from comments)

Before any LLM-produced reply is sent, a *second, cheaper* model is asked to interrogate it for unstated assumptions, overreach, or claims that lack supporting evidence. We adopt this as the third layer of citation defense, after regex extraction and DB existence check.

### 3.4 Anthropic — Model Context Protocol (MCP)
> https://modelcontextprotocol.io

**Core argument we adopt:** an agent's tools should be a stable, discoverable protocol, not a hand-rolled per-integration shim. We expose our data to *external* MCP clients (an advisor running their own Claude desktop can query our matrix via a hosted MCP server) and *consume* external MCPs from inside Agent Kenny (Slack, Linear, GDrive, when a tenant enables them).

### 3.5 LangGraph
> https://langchain-ai.github.io/langgraph/

**Core argument we adopt:** multi-step agent loops need an explicit state machine, not nested function calls. We use LangGraph for orchestrating the *retrieve → reason → tool-call → verify → revise → emit* cycle. Tool definitions and LLM calls go through the Anthropic SDK directly; LangChain itself is rejected as superseded.

---

## 4. The substrate (what we already have, viewed correctly)

DeployAI built the right primitives before we knew this was where we were going. The reframe is to *treat them as the wiki*:

| Substrate piece | Wiki role |
|---|---|
| `ledger_events` | The chronological log. Append-only timestamped record of everything that happened. |
| `ledger_event_causes` | Causal links between events. The provenance graph. |
| `ledger_event_affects` | Which entities each event touched. Enables "events affecting this node" queries. |
| `matrix_nodes` | The entity pages. Each row is one stakeholder / system / decision / risk / commitment / opportunity. |
| `matrix_nodes.attributes` (jsonb) | The page body. Today underused as a sparse blob; v2 enforces structured per-claim citation. |
| `matrix_edges` | The cross-references between entity pages. |
| `matrix_insights` | The synthesis layer. Agent-produced narrative summaries that compound over time. |
| `matrix_snapshots` | Time-travel. Daily snapshots of the whole matrix for "what did we know on day N" queries. |
| `oracle_chat_turns` | Per-conversation working memory. Kenny's recent dialogue with the strategist team. |
| `temporal_insights` | Periodic analyzer outputs (silence, decision-cycle slowdown, etc.). Generated synthesis. |

**This is the wiki.** It does not need a markdown shadow copy. It needs discipline applied to it.

---

## 5. Principles in tension and how we resolve them

### 5.1 Compound vs. ephemeral

**Principle:** Synthesis that took LLM tokens to produce should persist as a typed row, not be recomputed.

**Tension:** Aggressive caching of synthesis risks staleness. A decision-provenance summary written in week 4 may be wrong by week 14 if new evidence arrives.

**Resolution:** Every synthesized row carries `source_event_ids` it was derived from. The lint pass invalidates the row (marks `stale=true` + emits a `synthesis_stale_flagged` ledger event) if any source event is subsequently deleted, if new events causally upstream arrive, or if a contradicting decision lands. Kenny knows to refresh stale synthesis before citing it.

### 5.2 Wide retrieval vs. tight prompts

**Principle:** Kenny should be able to traverse the engagement's full history.

**Tension:** Stuffing 10k tokens of context per turn is slow and expensive.

**Resolution:** Tiered retrieval. (1) Curated insights + matrix summary are always in the system prompt — small, dense, citation-bound. (2) Tool calls fetch on-demand for specific queries (causal chain walk, full node attributes). (3) Vector search is the fuzzy fallback. Kenny chooses depth; budget caps prevent runaway loops.

### 5.3 Speed vs. verification

**Principle:** Every reply must be verifiable. No hallucinated citations.

**Tension:** Multi-pass verification adds latency.

**Resolution:** Citation verification runs *during* streaming, not after. As deltas arrive, citation regex matches are queued for DB lookup. If a citation fails by the time the `done` frame arrives, the reply is either revised once or rendered with an inline warning. Latency added: <100ms.

### 5.4 Autonomy vs. auditability

**Principle:** Kenny should reason multi-step, calling tools as needed.

**Tension:** A multi-step agent loop is opaque. Strategists can't see why Kenny said what he said.

**Resolution:** Every tool invocation is a ledger event. Every reply emits `agent_audit_trace` linking back to the full chain of tool calls + LLM completions + citation verifications. The whole reasoning trail is reconstructable from the ledger. Auditability is not a feature; it is the foundation.

### 5.5 Power vs. blast radius

**Principle:** Kenny should be useful — propose actions, draft updates, integrate with external systems.

**Tension:** A write-capable AI is a write-capable hallucination vector.

**Resolution:** Kenny has exactly one write-capable tool: `propose_action`, which inserts into `strategist_action_queue_items` for human review. He never writes to `matrix_nodes`, `matrix_edges`, or `ledger_events` directly. Every Kenny-originated change passes through a human queue. This is non-negotiable for compliance buyers.

---

## 6. What "good" looks like at v2 ship

A strategist asks Kenny:

> *"Did anyone raise concerns about the Active Directory migration before we approved it in W22?"*

Kenny, with the v2 plan in place, does:

1. **Retrieves curated index** — the matrix index synthesis says "AD migration" is a decision node with id `decision-ad-migration-uuid`.
2. **Calls `walk_chain`** on the `proposal_accepted` event for that decision, upstream direction.
3. **Reads the causal chain** — three `narrative` events from W19–W21 cite the AD topic.
4. **Calls `get_matrix_node`** for the affected stakeholder nodes (security team + customer IT lead) to read their per-claim cited descriptions.
5. **Replies in 3 sentences:**
   > "Two concerns were raised pre-approval. The customer security team flagged credential rotation timing in W19 [event:abc...]. IT lead Jane Park warned about Kerberos delegation in W20 [event:def...]. Both were resolved in the W22 approval meeting [event:ghi...]."
6. **Adversarial review** — second model checks: are there other unmentioned concerns? It finds none in the cited chain. Pass.
7. **Citation verification** — every `[event:…]` cite resolves to a real row in this engagement. Pass.
8. **Emits `agent_audit_trace`** linking the reply to all 5 citations + 3 tool calls.

Latency: ~6s. Token cost: ~$0.02. Every claim verifiable.

That is the bar.

---

## 7. Decisions that are open

These get answered as we build:

- **Embedding model:** Voyage-3 (Anthropic) or `text-embedding-3-large` (OpenAI). Lean Voyage for vendor coherence.
- **Apache AGE vs. recursive CTEs:** Install AGE if `walk_chain` performance degrades on XL fixture; otherwise CTEs suffice. Decision point at end of Phase 0.
- **Adversarial reviewer model:** Haiku 4.5 (cheap, fast) vs. Sonnet 4.6 (more thorough). Start with Haiku, instrument the eval harness, escalate if false-positive rate on missed concerns > 5%.
- **Lint cadence:** Event-triggered (lint affected rows after every relevant ledger emit) vs. nightly cron. Default to event-triggered with a nightly safety net.

---

## 8. When to revisit this ethos

Trigger conditions:

- **Multi-engagement portfolio reasoning becomes a stated product feature.** Cross-engagement traversal may need different substrate.
- **Single engagement exceeds 50k matrix nodes.** AGE may no longer scale; revisit Neo4j or a dedicated graph store.
- **A paying customer requires an air-gapped on-prem deployment.** MCP outbound (Slack/Linear/etc.) may need to be cut entirely.
- **Compliance regulator requires explicit "approval before AI may read this data."** Adds an authorization layer atop the retrieve path; rethink the autonomy/auditability balance.

Until one of those triggers fires, this ethos stands.

---

## 9. One-line summary

**The ledger is the wiki. Kenny is its disciplined librarian. Every claim cites its source; every reply is auditable; every synthesis compounds.**
