# Agent Kenny — LLM Wiki origin

**Status:** v2 build COMPLETE as of 2026-05-27. Phases 0 through 6 shipped on
`main`.
**Last updated:** 2026-05-27.
**Audience:** Someone who has read (or will read) Andrej Karpathy's *LLM Wiki*
gist and wants to understand which parts of the pattern shipped verbatim into
DeployAI and which parts we deliberately changed.
**Companion docs:** [`ethos.md`](./ethos.md) §3.1 for the original
inspiration callout; [`graph-substrate.md`](./graph-substrate.md) for the
substrate the wiki idea was adapted into; [`scope-v2.md`](./scope-v2.md) §16
for the inspiration table; [`../design/timeline-ledger.md`](../design/timeline-ledger.md)
for the ledger primitive everything builds on.

---

## 1. The Karpathy idea (one paragraph)

The gist: <https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f>.

Karpathy describes an LLM workflow where instead of retrieval-augmented
generation against raw documents on every query, the LLM "incrementally builds
and maintains a persistent wiki — a structured, interlinked collection of
markdown files." Sources are ingested once and integrated into the wiki via
LLM-generated entity pages, concept pages, an `index.md` catalog, and an
append-only `log.md` history. A configuration document (e.g. `CLAUDE.md`)
defines the conventions. The LLM periodically lints the wiki for
contradictions, stale claims, orphan pages, missing cross-references, and data
gaps. Index-based lookup is preferred to embeddings at moderate scale (~100
sources). Crucially, "good answers can be filed back into the wiki as new
pages" — explorations compound. The human curates sources and asks questions;
the LLM does "the summarizing, cross-referencing, filing, and bookkeeping."

---

## 2. What we kept verbatim

### 2.1 Compounding synthesis over re-synthesis

Karpathy's wiki is a compounding artifact — every ingest enriches it, every
good answer files back as a page. We adopted this as the core posture of the
substrate: synthesis that took LLM tokens to produce **persists as a typed
row, not as transient context**. Three synthesis kinds —
`decision_provenance`, `risk_explainer`, `stakeholder_brief` — are written
once when their triggering event lands and refreshed on subsequent triggers.
See [`graph-substrate.md`](./graph-substrate.md) §4 for the worker,
`services/control-plane/src/control_plane/workers/synthesizer.py` for the
code, and `services/control-plane/alembic/versions/20260613_0043_synthesis_compounding.py`
for the schema.

### 2.2 Per-claim citations enforced

Karpathy's pattern leans on links between pages and sources. We took the
stricter Synthadoc commenter version (ethos §3.2): every prose paragraph
carries at least one `[event:UUID]` or `[node:UUID]` / `[insight:UUID]`
citation. The synthesizer worker validates this on write via
`control_plane/agents/synthesis/claim_cite.py`; rows that fail validation
get one retry and then emit a `synthesis_validation_failed` ledger event
instead of corrupting the substrate. Phase 3 enforces the same rule on
every Kenny reply — citations are parsed during streaming, looked up
against `ledger_events` scoped to the current tenant + engagement, and
unverifiable claims either get revised once or shipped with an inline
warning (scope-v2 §7).

### 2.3 Lint pass over curated content

Karpathy lists five lint failure modes (contradictions, stale claims, orphan
pages, missing cross-references, data gaps). We mapped this directly into
`services/control-plane/src/control_plane/workers/wiki_lint.py` (Phase 0.6)
with five checks that landed in `0044_lint_flags.py`:

```
contradiction | stale | orphan | missing_cite | broken_cite
```

The worker is **flags-only**: it writes rows to `lint_flags` and emits
ledger events but never mutates curated prose (the one exception is marking
insights `stale=true`, which is metadata, not content). Triggers: inline
after every `proposal_accepted`, `matrix_node_updated`, `insight_opened`,
`insight_closed` ledger event; plus a 04:00 UTC cron sweep. Surfaced on the
admin dashboard alongside hallucination rate.

### 2.4 Adversarial review

The adversarial-reviewer pattern is from the gist comments (Synthadoc) rather
than the main gist body, but the pairing with curated synthesis was a clean
fit. Phase 3 wires a second LLM call (Haiku 4.5 by default) that reads each
draft Kenny reply + the cited evidence and lists concerns: unstated
assumptions, claims not supported by evidence, overconfident generalizations.
See `services/control-plane/src/control_plane/agents/agent_kenny/nodes/adversarial.py`
and scope-v2 §7.3 for the rubric. Concerns are recorded in
`agent_audit_traces`; they only block ship when paired with a citation
failure.

### 2.5 Index-first, embeddings-as-fallback at moderate scale

Karpathy's empirical observation — index-based retrieval beats embedding
search up to roughly hundreds of sources — held in our scale (BlueState seed:
7 stakeholders, 20 decisions, 13 risks, 249 ledger events; BlueState-XL is
~10x). Vector search shipped in Phase 5.5 as the **fallback** path:
`vector_search` is one of twelve agent tools, not the default. Curated
synthesis is the hot path. See [`graph-substrate.md`](./graph-substrate.md)
§5.4 and ethos §6 for the "fallback ≠ primary" reasoning.

### 2.6 LLM-judge eval discipline

Not from the gist directly, but in the same family of ideas the gist
encourages — measuring an LLM-produced artifact with an LLM judge.
Phase 6 ships a 30-question golden set against BlueState-XL with per-question
metrics (latency, tool calls, citation counts, revisions, adversarial
concerns, `cross_engagement_leak`, an LLM-judge semantic match against the
expected answer). See [`eval.md`](./eval.md) and
`services/control-plane/tests/golden/agent_kenny/`.

---

## 3. What we changed and why

### 3.1 No parallel markdown filesystem — the substrate *is* the wiki

The single biggest deviation. Karpathy's wiki lives in markdown files on
disk, navigable as a folder tree, editable in Obsidian. We considered a
parallel `engagement_wikis/<id>/*.md` projection next to Postgres and rejected
it. The reasons:

| Markdown FS would need | Postgres already gives us |
|---|---|
| Its own access control layer for multi-tenant isolation. | Row-level scoping via `tenant_id` / `engagement_id` on every table. |
| A sync protocol with the ledger to preserve the audit chain. | Same-transaction emit: `matrix_node_created` + the ledger row land together; a rollback drops both. |
| A custom validator for cross-page links. | FK arrays (`citation_event_ids`, etc.) referencing real UUIDs in `ledger_events` / `matrix_nodes`. |
| Its own index for dashboard aggregations (hallucination rate, lint counts, tool histograms). | Plain SQL `GROUP BY` over the same tables the writes land in. |
| A backup story scoped per tenant. | `pg_dump` filtered on `tenant_id` is already the contract. |

Karpathy's atoms are markdown files; ours are `matrix_nodes` rows +
`matrix_insights` synthesis rows. A "page" is a synthesis row; a "fact" is a
`ledger_events` row; a "cross-reference" is a `matrix_edges` row. The wiki
view is rendered by the web app at `/engagements/{id}/matrix` from the same
tables; markdown is at most an *export* projection generated on demand, never
the source of truth.

### 3.2 Per-node granularity, not per-file

Karpathy's pattern updates whole markdown files: the LLM ingests a source,
appends to an entity page, refreshes the index, writes a log entry. Our
granularity is the row. A `decision_provenance` refresh upserts exactly one
`matrix_insights` row keyed by `dedup_key = kenny:decision_provenance:{node_id}`.
A new `proposal_accepted` event enqueues exactly one
`synthesis_refresh_jobs` row whose worker upserts that one insight.

This made transactional safety free — the ledger event, the synthesis-job
enqueue, and the synthesis-row upsert each land in their own transaction with
their own consistency guarantees, and never partial-write a page that's been
half-edited.

### 3.3 Curated-by-humans-with-LLM-assist, not LLM-writes-directly

Karpathy's setup trusts the LLM to write into the wiki. Ours doesn't —
extraction proposes, humans accept or reject. Every matrix mutation flows
through `MatrixProposal` (table `matrix_proposals`, ORM in
`services/control-plane/src/control_plane/domain/canonical_memory/matrix.py`)
and the accept route is the only path that mints `matrix_nodes` /
`matrix_edges` rows. The agent itself has exactly one write-capable tool:
`propose_action` in
`services/control-plane/src/control_plane/agents/tools/escalate.py`, which
inserts into `strategist_action_queue_items` for human review.

Why we changed it: a single LLM hallucination that lands directly in the
substrate becomes a load-bearing "fact" that downstream synthesis cites,
that future Kenny replies cite, that the lint worker has no way to detect
unless it contradicts something else. The human-in-loop queue is the
cheapest insurance against compounding error in a system whose value
proposition is "every claim is verifiable" (ethos §5.5).

The synthesizer itself is the one place an LLM writes substrate rows
without explicit human review — but each row carries `agent='kenny'` for
auditability, must pass per-claim citation validation before commit, and is
re-checked by the lint worker on every triggering event after.

### 3.4 Curated reads, pgvector fallback (not embeddings-first)

Karpathy's reads are always whole-file: the index points the LLM at a
markdown file, the LLM reads it, done. Our reads are tiered:

```
1. Curated synthesis rows  (matrix_insights via read_synthesis)
2. Curated graph traversal (AGE Cypher via get_matrix_neighbors / _subgraph)
3. Curated event walks     (ledger_event_causes via walk_chain)
4. Keyword recall          (ILIKE via keyword_search)
5. Vector recall           (HNSW cosine via vector_search) — fallback only
```

The agent loop's `retrieve_initial_context` node
(`agents/agent_kenny/nodes/retrieve.py`) seeds the system prompt with the
engagement summary, open risks, and the last 30 days of ledger events —
small, dense, citation-bound. Tool calls layer in deeper context on demand.
`vector_search` is reached only when steps 1-4 return nothing useful.

This is the **fallback ≠ primary** rule from ethos §6. Cited authority comes
from the substrate. Vector hits are recall; they are not sourcing.

---

## 4. How the change shaped traversal

The four changes above propagated into the agent loop in concrete ways:

### 4.1 The retrieve node pulls curated context first

`retrieve_initial_context` reads three bundles before the LLM gets the
question: an engagement summary, open risks, and recent ledger events. All
three come from curated tables, all three carry their own citations. The LLM
opens its reasoning with cited material in hand, not with a vector hit it has
to trust.

### 4.2 Synthesis precomputation makes "what's the deal with X" cheap

Without Layer 3, a question like "what's the deal with risk R?" would mean
walking 200 events, summarizing them inline, and hoping the model doesn't
drop a cite. With Layer 3, that question is a single
`read_synthesis(target_id=R, insight_type="risk_explainer")` call — the
synthesis worker already did the walk, did the summary, did the cite
validation. Kenny inherits that work and reuses the same cites.

### 4.3 AGE handles path queries because curated edges are real graph data

Karpathy's wiki uses prose "see also" links between markdown pages. Ours uses
typed `matrix_edges` rows. Because those edges are real graph data — mirrored
into the `deployai_matrix` AGE view by the sync triggers (Layer 2) — multi-hop
queries like "all risks upstream of decision D via influence edges" reduce to
one Cypher `MATCH (r)-[:influences*1..4]->(d)`. No recursive CTE bookkeeping,
no markdown link-parsing.

### 4.4 Adversarial review is cheap because synthesis is short

The adversarial reviewer reads one synthesised page (2-4 paragraphs) plus
its cited evidence (a handful of ledger events), not the full ledger. That
is cheap enough to run on every reply — and we do.

---

## 5. What we'd revisit if/when the substrate-first bet breaks

The current bet is honest: at our scale (single engagements with hundreds to
low thousands of nodes, low tens of thousands of ledger events, multi-year
histories), curated synthesis + AGE traversal beats vector search for the
load-bearing claims. The fallback path exists for the misses.

Trigger conditions that would force a revisit:

- **A single engagement exceeds ~50k matrix nodes or ~1M ledger events.**
  AGE traversal latency starts to hurt; HNSW recall becomes attractive for
  rough "where to look" queries even before the curated read. (See also
  ethos §8 — same trigger forces a revisit of AGE vs Neo4j.)
- **Sub-100ms semantic retrieval becomes a hard chat UX requirement.**
  Today Kenny is allowed an 8s p90 budget (scope-v2 §6.6); a real-time
  product target would justify promoting vector search to a parallel-with-
  curated path, then merging results.
- **A customer requires multi-engagement portfolio reasoning by Kenny.**
  Cross-engagement curated synthesis is a different shape than per-
  engagement — the dedup key, the citation scoping rules, and the lint
  checks all assume single-engagement today.
- **Compliance regulator forbids LLM writes to the substrate at all.** The
  synthesizer worker is the one LLM writer of `matrix_insights` rows; a
  hard ban would push synthesis into a separate review queue, slowing the
  compound loop but preserving the "curated reads" property.

Until one of those fires, the substrate is the wiki, and the wiki is the
substrate.

---

## 6. One-line summary

**Karpathy gave us the compounding-curated-knowledge pattern; we kept the
discipline (citations, lint, adversarial review, index-first) and traded
his markdown filesystem for a Postgres substrate with an AGE overlay, a
human-in-loop accept queue, and a vector fallback. Same idea, different
atoms.**
