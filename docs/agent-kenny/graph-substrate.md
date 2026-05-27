# Agent Kenny — the graph substrate

**Status:** v2 build COMPLETE as of 2026-05-27. Every layer described below is
shipped on `main` and exercised by every Kenny turn.
**Last updated:** 2026-05-27.
**Audience:** A senior engineer or curious customer who wants to understand the
data model that powers the matrix view and every cited answer Kenny produces.
**Companion docs:** [`ethos.md`](./ethos.md) for *why* the substrate is shaped
this way; [`scope-v2.md`](./scope-v2.md) for the ship record;
[`llm-wiki-origin.md`](./llm-wiki-origin.md) for what we kept vs changed from
Karpathy's gist; [`../design/timeline-ledger.md`](../design/timeline-ledger.md)
for the ledger that drives everything below.

---

## 1. What "substrate" means here

"Substrate" is the word DeployAI uses for the durable, curated knowledge layer
Kenny reads from. It is **not** a graph database in the Neo4j sense. It is a
relational store (Postgres) with three additional layers stacked on top, each
with a single job:

| Layer | Storage | Job |
|---|---|---|
| 1. Canonical memory | Postgres tables | Source of truth — every node, edge, insight, event lives here under tenant + engagement scope, with FK integrity for citations. |
| 2. Apache AGE Cypher overlay | `deployai_matrix` graph view inside the same Postgres | Cheap path queries (`MATCH … *1..k`) that would be ugly recursive CTEs against tables. |
| 3. Curated synthesis | `matrix_insights` rows produced by the synthesizer worker | Compounding "wiki pages" — `decision_provenance`, `risk_explainer`, `stakeholder_brief` — refreshed on event triggers, each with per-claim citations. |
| 4. pgvector fuzzy fallback | `embedding vector(1024)` column on four source tables | Voyage-3 cosine recall over ledger / nodes / insights / chat turns when curated lookup misses. |

The contract across all four layers is **one Postgres cluster**. No second
source of truth, no markdown shadow, no separate graph store. Layers 2-4 are
populated by triggers and workers so application code never has to remember to
write to more than one place.

```
                        +-------------------------------------------+
                        |               Postgres cluster            |
                        |                                           |
   write path           |   Layer 1 — canonical memory (tables)     |
   (ledger emit         |     ledger_events                         |
    + matrix CRUD)      |     matrix_nodes / matrix_edges           |
                        |     matrix_insights                       |
                        |                                           |
                        |   Layer 2 — AGE overlay (triggers)        |
                        |     deployai_matrix Cypher graph          |
                        |     (MERGE on every matrix_* write)       |
                        |                                           |
                        |   Layer 3 — synthesis (worker)            |
                        |     synthesis_refresh_jobs queue          |
                        |     matrix_insights rows (agent='kenny')  |
                        |                                           |
                        |   Layer 4 — embeddings (worker)           |
                        |     vector(1024) col on 4 tables          |
                        |     embedding_jobs queue + HNSW indexes   |
                        +-------------------------------------------+
                                          ^
                                          |
                                  Kenny tool catalog
                                  (12 read tools + 1 write)
```

---

## 2. Layer 1 — canonical memory (the relational core)

The first layer is plain Postgres tables. Everything Kenny ever cites traces
back to a row here.

### 2.1 The five tables that matter most

| Table | Role | Migration |
|---|---|---|
| `engagements` | One deployment scope per row; multi-tenant via `tenant_id`. | (pre-v2) |
| `ledger_events` | Append-only causal log: who did what, when, why, with `source_kind` taxonomy and `detail` jsonb. | `0034_ledger_events.py` (pre-v2) |
| `ledger_event_causes` / `ledger_event_affects` | The causal DAG: `caused_by` edges between events + `affects` edges from events to matrix entities. | `0035` / `0036` |
| `matrix_nodes` | Typed entities (`node_type`: stakeholder, organization, system, decision, risk, commitment, opportunity). | `services/control-plane/alembic/versions/20260601_0020_matrix_nodes_edges.py` |
| `matrix_edges` | Typed directional links between nodes (`edge_type`: influences, blocks, depends_on, …). | same migration |
| `matrix_insights` | Synthesis outputs (one row per `dedup_key`); cite-bearing prose with `citation_event_ids`, `citation_node_ids`, `citation_edge_ids`. | `0024` extended by `0043_synthesis_compounding.py` |

The full schema is documented inline in
`services/control-plane/src/control_plane/domain/canonical_memory/matrix.py`
(`MatrixNode`, `MatrixEdge`, `MatrixInsight`, `SynthesisRefreshJob`) and in
[`../design/timeline-ledger.md`](../design/timeline-ledger.md) §3 for the
ledger.

### 2.2 Why relational, not "pure graph"

A naive read of "knowledge graph" suggests Neo4j or a triplestore. We chose
relational for four reasons that have not yet bitten us:

- **Multi-tenant RLS.** Every row carries `tenant_id` and (where applicable)
  `engagement_id`; cross-tenant isolation is enforced at the Postgres layer.
  A separate graph store would need its own isolation discipline maintained
  in parallel.
- **Transactional writes paired with ledger entries.** When the human accepts
  a `MatrixProposal`, the same transaction that flips the proposal row,
  inserts the `matrix_node`, and emits the `proposal_accepted` ledger event
  succeeds or rolls back as a unit. There are no phantom matrix rows without
  a ledger entry, ever.
- **FK integrity for citations.** Every `matrix_insight` carries arrays of
  `citation_event_ids` / `citation_node_ids` / `citation_edge_ids`. A
  citation that points at a nonexistent row is a bug we want to catch via
  lint (Phase 0.6) rather than a structural impossibility — but the cite
  format is itself UUIDs of real tables, not free-text URIs.
- **SQL aggregations for dashboards.** The admin dashboard
  (`apps/web/src/app/(strategist)/admin/agent-kenny-dashboard/`) reads
  hallucination rate, tool-call distribution, lint flag counts, and citation
  histograms via straight SQL. A graph store would need a parallel index.

### 2.3 How a node or edge is born

The lifecycle of every matrix mutation closes a loop through the ledger:

```
1. raw event lands             (e.g. email_ingest → ledger_event)
2. extractor proposes          (matrix_proposals row, status='pending'
                                + ledger event 'llm_proposal_created')
3. human reviews + accepts     (PATCH /matrix-proposals/{id}
                                → matrix_proposals.status='accepted'
                                + matrix_nodes / matrix_edges INSERT
                                + ledger event 'proposal_accepted'
                                + ledger event 'matrix_node_created'
                                + ledger_event_affects row pointing at the new node)
4. AGE trigger fires           (MERGE node into deployai_matrix — Layer 2)
5. synthesis trigger fires     (synthesis_refresh_jobs row enqueued — Layer 3)
6. embedding trigger fires     (embedding_jobs row enqueued — Layer 4)
```

The accept route is the *only* way matrix rows are born. Kenny himself does
not have a write tool for `matrix_nodes` or `matrix_edges`; his single write
tool is `propose_action`, which inserts into
`strategist_action_queue_items` for human review (ethos §5.5).

### 2.4 Audit + immutability

`ledger_events` is append-only in the normal flow. Every mutation that
touches the substrate lands a ledger row inside the same transaction; a
rollback drops both. The cause/affect tables use `ON DELETE CASCADE` so
hard-deleting an admin-redacted event also drops its causal edges, leaving
no dangling references.

---

## 3. Layer 2 — the Apache AGE Cypher overlay

Postgres tables make excellent storage for relational truth but ugly storage
for graph traversals — recursive CTEs work, but they are awkward to write,
hard to read, and limited in what they can express ergonomically. Layer 2
adds a Cypher view over the same data without introducing a second database.

### 3.1 What `0042_apache_age.py` installed

`services/control-plane/alembic/versions/20260613_0042_apache_age.py` does
three things:

1. `CREATE EXTENSION IF NOT EXISTS age` (wrapped in a `DO` block that
   warns-and-continues on managed Postgres providers that lack the AGE
   binary — the legacy testcontainer falls into this path).
2. `create_graph('deployai_matrix')` — one graph per cluster, shared
   across tenants; isolation is enforced by property filter, not by graph
   partition (see §3.3).
3. Installs two trigger functions —
   `matrix_nodes_age_sync_trigger()` and `matrix_edges_age_sync_trigger()`
   — that mirror writes from `matrix_nodes` / `matrix_edges` into the AGE
   graph on every INSERT / UPDATE / DELETE.

The trigger bodies live in
`services/control-plane/src/control_plane/domain/canonical_memory/age_sync.py`
so the SQL is reviewable in isolation; the migration just imports the
strings and `op.execute()`s them.

### 3.2 How the sync triggers work

Node trigger, abbreviated:

```sql
MERGE (n:matrix_node {id: <new.id>})
SET n.tenant_id     = <new.tenant_id>,
    n.engagement_id = <new.engagement_id>,
    n.node_type     = <new.node_type>,
    n.title         = <new.title>
```

Edge trigger, abbreviated:

```sql
MATCH (a:matrix_node {id: <new.from_node_id>}),
      (b:matrix_node {id: <new.to_node_id>})
MERGE (a)-[r:<lower(edge_type)> {id: <new.id>}]->(b)
SET r.edge_type     = <new.edge_type>,
    r.tenant_id     = <new.tenant_id>,
    r.engagement_id = <new.engagement_id>
```

Edge labels are taken from the curated `MATRIX_EDGE_TYPES` catalog (lowercased
identifiers) — interpolation is safe because the catalog is closed. Both
trigger functions defensively `LOAD 'age'` and re-set the `search_path` per
session, because the database-level `ALTER DATABASE` only affects *new*
connections.

If the AGE binary is missing (legacy testcontainer, a managed provider that
won't load extensions), the trigger functions check `pg_extension` and silently
no-op — the canonical writes still commit, only the Cypher mirror is skipped.
Tool calls then fall back to recursive CTEs (see §3.4).

### 3.3 What this buys

Path queries that would be ugly recursive CTEs become straightforward Cypher:

```cypher
-- "all decisions upstream of risk R, via influence edges, up to 4 hops"
MATCH (d:matrix_node {type: 'decision', engagement_id: $eid, tenant_id: $tid})
      -[:influences*1..4]->
      (r:matrix_node {id: $riskId, engagement_id: $eid, tenant_id: $tid})
RETURN d
```

Tenant and engagement filters are required on *every* match because the graph
is shared across the cluster — there is one `deployai_matrix` graph, not one
per tenant. The helper `cypher_query(session, tenant_id, engagement_id, …)`
in `services/control-plane/src/control_plane/agents/tools/graph.py` enforces
this (`CypherIsolationError` is raised when a query is missing the required
filter clauses).

### 3.4 When Kenny uses it

Three of the twelve Phase 1 read tools prefer Cypher and fall back to
recursive CTEs when AGE is unavailable:

| Tool | Path | Why |
|---|---|---|
| `get_matrix_neighbors` | k-hop neighbors filtered by `edge_type` | `MATCH (n)-[r*1..k]-(m)` beats writing variable-depth SQL by hand. |
| `get_matrix_subgraph` | Bounded subgraph by `node_types` / `edge_types` / `since` | Multi-predicate graph filter is one line of Cypher, many lines of SQL. |
| `walk_chain` (ledger) | Causal-chain walk over `ledger_event_causes` | Same shape, applied to events instead of matrix nodes. |

See `services/control-plane/src/control_plane/agents/tools/matrix.py`
(`_neighbors_via_cypher` + `_neighbors_via_cte`) for both code paths side
by side.

### 3.5 Trade-off note

The AGE view is a **second source of truth**. We accept this because it is
kept consistent by triggers, not by application code. No writer ever has to
remember to update the graph view; the trigger is the contract. The day a
trigger drifts from the table is the day this trade-off bites — which is why
the AGE migration installs both the function and the attach DDL together,
and why the trigger code lives in `age_sync.py` for review.

---

## 4. Layer 3 — curated synthesis (the compounding wiki layer)

Layer 1 stores facts. Layer 2 makes traversal cheap. Layer 3 is what makes
the substrate behave like a *wiki* — pages that compound over time and that
Kenny can read directly instead of re-deriving from raw events on every turn.

### 4.1 What `0043_synthesis_compounding.py` added

`services/control-plane/alembic/versions/20260613_0043_synthesis_compounding.py`:

- Extended `matrix_insights` with `last_refreshed_at`, `stale`, and a CHECK
  that synthesis rows (`agent = 'kenny'`) carry at least one
  `citation_event_id` (per scope-v2 §3.1).
- Widened the `agent` enum to include `'kenny'` alongside `'oracle'` and
  `'master_strategist'`.
- Added the `synthesis_refresh_jobs` queue table with three job kinds —
  `decision_provenance`, `risk_explainer`, `stakeholder_brief` — and four
  statuses (`pending`, `running`, `done`, `failed`).

### 4.2 Three kinds of synthesis the substrate maintains

| Kind | Target | Triggered by | Output |
|---|---|---|---|
| `decision_provenance` | one `decision` `matrix_node` | `proposal_accepted` whose `detail.node_type == 'decision'` | 2-4 paragraph cited summary of *why this decision exists*, anchored on the upstream causal chain back to the triggering events |
| `risk_explainer` | one high-severity `MatrixInsight` (the risk) | `insight_opened` with `detail.severity == 'high'` | cited explainer: what the risk is, why it matters, who is affected, current state |
| `stakeholder_brief` | one stakeholder `matrix_node` | `matrix_node_created` whose `detail.node_type == 'stakeholder'` *or* `member_added` carrying a `stakeholder_node_id` hint | cited brief: what this stakeholder cares about, what they've decided, latest signals |

Each synthesis output is one row in `matrix_insights` keyed by a
deterministic `dedup_key` (e.g. `kenny:decision_provenance:{node_id}`) so
refresh upserts in place.

### 4.3 Trigger routing in the ledger emitter

The routing rules above are not aspirational — they are encoded in
`services/control-plane/src/control_plane/ledger/emitter.py` inside
`_maybe_enqueue_synthesis`. Every `emit_ledger_event` call that lands an
`engagement_id` runs the dispatcher. The exact rules:

```python
if src == "proposal_accepted":
    # detail.node_type hint preferred; falls back to a matrix_nodes lookup
    if node_type == "decision":
        for target_id in affected_matrix_nodes:
            triggers.append(("decision_provenance", target_id))

elif src == "insight_opened" and detail.get("severity") == "high":
    for kind, target_id in affects:
        if kind == "insight":
            triggers.append(("risk_explainer", target_id))

elif src == "matrix_node_created" and detail.get("node_type") == "stakeholder":
    for kind, target_id in affects:
        if kind == "matrix_node":
            triggers.append(("stakeholder_brief", target_id))

elif src == "member_added":
    stakeholder_node_id = detail.get("stakeholder_node_id")
    if isinstance(stakeholder_node_id, str):
        triggers.append(("stakeholder_brief", uuid.UUID(stakeholder_node_id)))
```

Each trigger appends one `SynthesisRefreshJob` row (status `pending`) inside
the same transaction as the originating event. A rollback drops both.

### 4.4 How the worker computes synthesis

`services/control-plane/src/control_plane/workers/synthesizer.py` exposes
three entrypoints — `refresh_decision_provenance`,
`refresh_risk_explainer`, `refresh_stakeholder_brief` — one per `kind`. They
share the same shape:

1. **Find the anchor** — the most recent triggering event affecting the
   target (`_find_anchor_event`), preferring the `trigger_event_id` recorded
   on the job row.
2. **Walk the causal chain** upstream from the anchor up to
   `_CHAIN_MAX_DEPTH=4` / `_CHAIN_MAX_NODES=20`. (`_walk_causal_chain`.)
3. **Format prompt context** — a structured rendering of the anchor + chain
   events with their UUIDs intact so the model can cite them.
4. **Call the tenant-resolved LLM provider** with a structured-output
   instruction: "Reply ONLY with JSON of shape `{title, body, claim_citations:
   [{paragraph, event_ids}]}` … EVERY paragraph MUST embed at least one
   inline citation tag `[event:UUID]` referencing the supplied event ids.
   Do not invent ids."
5. **Validate per-claim citations** with
   `control_plane/agents/synthesis/claim_cite.py` — rejects on missing or
   broken cites, retries once, then emits a `synthesis_validation_failed`
   ledger event instead of corrupting the substrate.
6. **Upsert one `matrix_insights` row** keyed by `dedup_key`, with `agent =
   'kenny'`, the synthesised body, and the validated `citation_event_ids`.

The drain endpoint `POST /internal/v1/admin/synthesis/drain` (Phase 0.6
replaces this with a cron worker) pulls pending jobs and routes by `kind`.

### 4.5 Why this matters for the agent

When Kenny needs "what's the deal with risk R?", he does not replay the
chain of 200 ledger events that produced the risk. He reads the already-
synthesised `kenny:risk_explainer:{R}` row from `matrix_insights` via the
`read_synthesis` tool and cites the same source events the synthesizer
itself cited (those UUIDs are in `citation_event_ids`).

The Phase 3 verifier later re-checks each cite against `ledger_events` in
the current tenant + engagement. The synthesis row is trusted because the
substrate is trusted, but the cite-validation discipline is the same as for
any other Kenny output.

This is the "compounding" property from ethos §2: synthesis that took LLM
tokens to produce persists as a typed row instead of being recomputed on
every turn.

---

## 5. Layer 4 — pgvector fuzzy fallback (Phase 5.5)

Layers 1-3 give Kenny cited, curated reads. Layer 4 catches the misses:
queries vague enough that the strategist can't name the node, or where no
synthesis row has been written yet.

### 5.1 What `0050_pgvector_embeddings.py` added

`services/control-plane/alembic/versions/20260613_0050_pgvector_embeddings.py`:

- `CREATE EXTENSION IF NOT EXISTS vector` (pgvector).
- `ALTER TABLE … ADD COLUMN embedding vector(1024)` on four source tables:
  - `ledger_events`
  - `matrix_nodes`
  - `matrix_insights`
  - `oracle_chat_turns`
- HNSW cosine index per column (`vector_cosine_ops`) — Voyage-3 is
  normalized for cosine, and HNSW does not need a training rebuild so the
  indexes can be created empty.
- A new `embedding_jobs` queue table (unique on `(source_table, source_id)`).
- An `AFTER INSERT OR UPDATE` trigger on each of the four tables that
  upserts into `embedding_jobs` with `status='queued'`. The conflict path
  resets to `queued` so a fresh update bumps the row even mid-flight.

### 5.2 The worker

`services/control-plane/src/control_plane/workers/embedder.py` polls the
queue, batches up to N rows per Voyage-3 API call (1024-dim output), and
writes back into the corresponding `embedding` column. Status moves `queued
→ running → done` (or `failed` with an `attempts` counter for retry
budgeting).

### 5.3 The tool

`vector_search` in
`services/control-plane/src/control_plane/agents/tools/search.py` is the only
agent-facing surface for Layer 4. It takes a kind (`event` / `node` /
`insight` / `turn`), a query string, embeds the query with the same Voyage-3
model, and returns the top-N cosine-similar rows scoped to the current
tenant + engagement.

### 5.4 Why fallback, not primary

Per [`ethos.md`](./ethos.md) §6: cited authority comes from the substrate.
Vector hits are *recall*, not *sourcing*. A typical Kenny turn reads
curated synthesis first (one row), walks chains via tools as needed, and
only falls back to `vector_search` when the curated path returns nothing
useful. This ordering is enforced by the agent loop's tool catalog and by
the Phase 6 eval harness — multi-hop questions are expected to hit AGE
traversal, not embeddings, for the load-bearing claims. See
[`llm-wiki-origin.md`](./llm-wiki-origin.md) §3 for the "fallback ≠
primary" reasoning end-to-end.

---

## 6. Traversal example — end to end

Question (from the Phase 6 eval set,
`services/control-plane/tests/golden/agent_kenny/questions.yaml`):

> *"What risks are upstream of the SSO migration decision that mention legal?"*

The agent loop walks the substrate like this:

1. **Locate the decision node.** Kenny calls `keyword_search(q="SSO
   migration", kinds=["node"])` or `get_matrix_subgraph(node_types=
   ["decision"], …)` to find the decision node id. (`keyword_search` and
   `get_matrix_subgraph` are both in
   `services/control-plane/src/control_plane/agents/tools/`.) Result:
   `decision-sso-migration-uuid`.

2. **Walk upstream via AGE.** Kenny calls `get_matrix_neighbors(node_id=
   <sso>, k=4, edge_types=["influences", "blocks"])`. Under the hood,
   `_neighbors_via_cypher` runs:

   ```cypher
   MATCH (n:matrix_node {id: '<sso>', tenant_id: $tid, engagement_id: $eid})
         -[r:influences|blocks *1..4]-
         (m:matrix_node {tenant_id: $tid, engagement_id: $eid})
   WHERE m.id <> '<sso>'
   RETURN DISTINCT m.id AS mid LIMIT 100
   ```

   Result: a set of neighbor node UUIDs; Kenny narrows to those with
   `node_type='risk'`.

3. **Read the curated risk explainers.** For each candidate risk, Kenny calls
   `read_synthesis(target_id=<risk>, agent="kenny", insight_type=
   "risk_explainer")`. Each call returns the precomputed
   `kenny:risk_explainer:{risk}` row from `matrix_insights` — a 2-4
   paragraph cited prose body that the synthesizer worker wrote when the
   risk was first opened.

4. **Filter on "legal" in the synthesised text** *and* in the underlying
   event summaries (the cite UUIDs are right there in `citation_event_ids`,
   so a final `query_ledger` lookup hydrates the source summaries cheaply).

5. **Build the cited reply.** Kenny writes 2-3 sentences naming the
   matching risks and citing them as `[event:UUID]` — and crucially, *the
   citations come from the synthesis row, not from Kenny inventing them*.
   The synthesizer worker already validated those cites against
   `ledger_events`; Kenny is reusing trusted material.

6. **Verify before streaming.** The Phase 3 verifier
   (`agents/agent_kenny/nodes/citations.py`) re-parses every `[event:UUID]`
   token from the reply and checks each id exists in `ledger_events`
   scoped to the current tenant + engagement. Unknown cites trigger a
   single revision attempt; cross-engagement cites trigger a hard reject
   (`cross_engagement_leak` security event) and the reply is replaced with
   "I'm unable to answer that question."

7. **Adversarial review.** Haiku 4.5 reads the reply + evidence and flags
   unstated assumptions or overreach
   (`agents/agent_kenny/nodes/adversarial.py`). Concerns are logged to
   `agent_audit_traces`; they don't block ship unless paired with a
   citation failure.

8. **Persist the audit trace + stream `done`.** `agents/agent_kenny/nodes/
   persist.py` writes one row to `agent_audit_traces` linking the reply to
   every tool call and citation outcome — the whole reasoning trail is
   reconstructable from the ledger.

The tools used in steps 1-3 — `keyword_search`, `get_matrix_subgraph`,
`get_matrix_neighbors`, `read_synthesis`, `query_ledger` — are five of the
twelve registered in
`services/control-plane/src/control_plane/agents/tools/__init__.py`
(`TOOL_REGISTRY`). The full twelve (per the Phase 1 layer):

```
query_ledger          walk_chain
get_matrix_node       get_matrix_neighbors      get_matrix_subgraph
read_synthesis        get_decision_history      get_open_risks
get_engagement_summary
keyword_search        vector_search
propose_action        (the only write tool)
```

---

## 7. Extraction quality controls

Three controls keep the substrate honest:

### 7.1 Lint worker (`workers/wiki_lint.py`)

`services/control-plane/src/control_plane/workers/wiki_lint.py` runs the
five checks defined in `0044_lint_flags.py`:

| Kind | Check |
|---|---|
| `contradiction` | Two `agent='kenny'` insights produced within a 14-day window sharing a `citation_node_id` where one body uses approval phrasing and the other rejection phrasing (v0 heuristic; LLM-assisted v1 is a TODO). |
| `stale` | Kenny/Oracle insights with `last_refreshed_at` older than 30 days *and* whose source events have causal descendants newer than the refresh timestamp. Mutates `stale=true` on the row in addition to flagging. |
| `orphan` | Insights whose `citation_event_ids` reference events no longer present in this tenant + engagement. |
| `missing_cite` | `matrix_nodes.attributes.description` paragraphs (blank-line separated) with zero `[event:…]` / `[node:…]` / `[insight:…]` cites. |
| `broken_cite` | Citation UUIDs parsed out of `matrix_nodes.attributes.description` or `matrix_insights.body` that do not resolve to a row in this tenant + engagement. |

The worker is flags-only — it does **not** mutate curated content (with the
one exception of marking insights `stale=true`, which is metadata, not
prose). Triggers: inline from the ledger emitter on `proposal_accepted`,
`matrix_node_updated`, `insight_opened`, `insight_closed`; plus a nightly
04:00 UTC cron sweep.

Flags land in the `lint_flags` table and surface on the admin dashboard
alongside hallucination rate.

### 7.2 Adversarial review (Phase 3)

A second LLM call (Haiku 4.5) reads every draft reply + evidence and
flags overreach before the reply ships. See ethos §3.3 and scope-v2 §7.3
for the prompt and the false-positive escalation rules.

### 7.3 Phase 6 eval harness

`services/control-plane/tests/golden/agent_kenny/questions.yaml` holds 30
hand-curated questions against BlueState-XL, distributed per
`tests/golden/agent_kenny/types.py::EXPECTED_DISTRIBUTION`:

```
direct_lookup: 8     causal_chain: 8     negative: 6
cross_engagement: 4  multi_hop: 4
```

The 8 `causal_chain` questions specifically test traversal correctness —
they require Kenny to walk events and matrix edges, not just direct
lookups. The runner records per-question metrics including citations
total / verified / unverified, revisions, adversarial concerns, and
`cross_engagement_leak` (a hard CI fail). See [`eval.md`](./eval.md) for
the full harness.

---

## 8. Reading the substrate yourself

The repeatable customer + new-engineer path:

1. `make dev` brings up the compose stack.
2. From the onboarding wizard pick **BlueState-XL** (or hit
   `POST /internal/v1/admin/seed-scenarios/bluestate-xl`). This seeds a
   5-year single-engagement fixture: ~70 stakeholders, ~200 decisions,
   ~130 risks, ~2.5k ledger events, ~600 edges, 1825-day snapshot
   backfill. Fixture code:
   `services/control-plane/src/control_plane/scenarios/bluestate_xl/`.
3. Open the engagement detail page → the matrix view renders the curated
   subgraph; the timeline view scrolls the ledger; the Kenny chat panel
   answers questions against everything above.
4. Open `/admin/agent-kenny-dashboard` to see hallucination rate, tool-call
   distribution, lint flag counts, and per-question eval results.
5. Poke the DB directly: `psql` into the cluster and explore `matrix_nodes`,
   `matrix_edges`, `matrix_insights`, `ledger_events`, `synthesis_refresh_jobs`,
   `lint_flags`, `embedding_jobs`. The AGE graph view is queryable via
   `SELECT * FROM cypher('deployai_matrix', $$ MATCH (n) RETURN n LIMIT 5
   $$) AS (n agtype);` after `LOAD 'age';`.

For tenant-isolation stress, the Portfolio fixture seeds 5 sibling
engagements × 26 weeks each; the cross-tenant fuzz suite
(`uv run pytest tests/fuzz`) probes every Kenny tool for leaks.

---

## 9. One-line summary

**Layer 1 is the truth; Layer 2 makes paths cheap; Layer 3 is the wiki;
Layer 4 is the fallback. Kenny reads top-down, cites bottom-up, and the
substrate is the only source of authority either way.**
