# DeployAI — Deployment-matrix model

| | |
| --- | --- |
| **Status** | Design / decision record. Phase 5 increment **5.1**. |
| **Date** | 2026-05-22 |
| **Drives** | Phase 5 increments 5.2–5.4 (schema, API, view, structured capture). |
| **Roadmap** | [`deployai-source-of-truth-spec.md`](./deployai-source-of-truth-spec.md) §16 — Phase 5. |
| **Substrate** | [`docs/canonical-memory.md`](../canonical-memory.md) — the canonical-memory schema this model extends. |

This document is the **decision record** for the deployment-matrix model. It is increment 5.1's deliverable: it does not ship code. Increment 5.2 builds the schema from it.

---

## 1. Why — the journal→map turn

Phases 1–4 delivered a manual engagement **journal**: `engagement_log_entries`, a chronological list of `meeting / decision / risk / next_action` notes. The product's goal — *map the complex matrix of a deployment, surface cross-team insight, spot opportunities to scale* — is a set of **queries over a structured graph**, not over free text. Phase 5 replaces the journal with a structured **map** of the deployment, built **on the canonical-memory substrate** rather than beside it.

The map is the foundation Phase 6 (ingestion) writes into and Phase 7 (the agents) reads.

---

## 2. The model — a typed property graph

A deployment is modelled as a **property graph**: typed **nodes** (the entities) joined by typed **edges** (the relationships), each carrying free-form `attributes` (JSONB) and provenance back to the canonical events that evidence it.

### 2.1 Node types (the entities)

Finalized set — seven node types:

| `node_type` | What it is |
| --- | --- |
| `stakeholder` | A person in the deployment (customer- or vendor-side). References a canonical `identity_node` — see §3.3. |
| `organization` | An org or org-unit — customer agency, department, vendor, partner. (The identity graph is people-only; this is new.) |
| `system` | A system, component, or asset being deployed or integrated. |
| `decision` | A decision taken — what, when, status. |
| `risk` | A risk — severity, likelihood, status. |
| `commitment` | A promise or obligation — owner, counterparty, due date, status. (Supersedes the journal's `next_action`.) |
| `opportunity` | A place to scale the account or introduce a new offering — the biz-dev payoff. |

**`interaction` is not a node.** A meeting / email / field note / manual entry is a **canonical event** (`canonical_memory_events`), not a matrix node — see §3.1. Nodes *cite* interactions; they are not interactions.

**Refinement from the §16 starter set:** the starter set listed *Dependency* as an entity. Finalized as an **edge type** (`depends_on`) — a dependency is a relationship between two things, not a thing.

### 2.2 Edge types (the relationships)

Edges are directional, typed, and connect two nodes. Starter set (extensible — see §6):

| `edge_type` | From → To |
| --- | --- |
| `belongs_to` | `stakeholder` → `organization` |
| `owns` / `sponsors` / `blocks` | `stakeholder` → `system` \| `decision` \| `commitment` |
| `affects` | `decision` → `system` |
| `threatens` | `risk` → `system` \| `decision` \| `commitment` |
| `owed_by` / `owed_to` | `commitment` → `stakeholder` |
| `depends_on` | `system` → `system`, `decision` → `decision` (etc.) |
| `enables` | `system` \| `stakeholder` → `opportunity` |

The exact verb set is not frozen — edge types are data (§6). What 5.1 fixes is the *shape*: directional typed edges between matrix nodes.

---

## 3. Where it lives — on canonical memory

**Decision: the matrix is a new property graph in the canonical-memory substrate, not a parallel store.** Two new tables, `matrix_nodes` and `matrix_edges`, in the same `public` schema, following canonical-memory conventions (§4). This is the convergence the re-scope calls for: the agents (Phase 7) query the matrix and the event log together.

### 3.1 Interactions = canonical events

A meeting / email / field note / manual entry is one row in `canonical_memory_events` — the existing immutable, append-only log. Phase 6 harnesses write events here (`event_type` = `email` / `meeting_note` / `field_note` / `manual_note`; `payload` = the normalized content). The matrix is *derived from* events.

### 3.2 Provenance — nodes and edges cite events

Every node and edge carries `evidence_event_ids UUID[]` — the canonical events it was derived from or is supported by. This reuses the established pattern from `solidified_learnings.evidence_event_ids` and keeps the matrix **retrieval-bound**: a node exists because events evidence it (FR1, the citation-envelope principle, §1/§11 of the spec). The map is reconstructable and auditable from the event log.

### 3.3 Stakeholders reuse the identity graph

A `stakeholder` node does **not** re-model a person. It carries `identity_node_id` → the canonical `identity_nodes` row. The identity graph already gives deduplication (FR2/FR3) and time-versioned role/title/email history (`identity_attribute_history`, DP11). The matrix node adds the *deployment-specific* framing (influence, disposition, where they sit in the matrix); the canonical identity stays the source of truth for *who they are*.

`organization` has no identity-graph equivalent (identity is people-only) — it is a plain matrix node.

---

## 4. Schema sketch

As built in increment 5.2a (`matrix_nodes` / `matrix_edges`, migration `0020`):

```
matrix_nodes
  id                 UUID  PK  DEFAULT deployai_uuid_v7()
  tenant_id          UUID  NOT NULL  FK app_tenants(id)  ON DELETE CASCADE
  engagement_id      UUID  NOT NULL  FK engagements(id)  ON DELETE CASCADE   -- born engagement-scoped
  node_type          TEXT  NOT NULL                            -- stakeholder | organization | system | ...
  title              TEXT  NOT NULL                            -- human label
  identity_node_id   UUID  NULL  FK identity_nodes(id) ON DELETE RESTRICT    -- set for stakeholder nodes
  attributes         JSONB NOT NULL DEFAULT '{}'               -- type-specific fields
  status             TEXT  NULL                                -- type-specific lifecycle
  evidence_event_ids UUID[] NOT NULL DEFAULT '{}'              -- canonical events this node cites
  created_at         TIMESTAMPTZ NOT NULL DEFAULT now()
  updated_at         TIMESTAMPTZ NOT NULL DEFAULT now()

matrix_edges
  id                 UUID  PK  DEFAULT deployai_uuid_v7()
  tenant_id          UUID  NOT NULL  FK app_tenants(id)  ON DELETE CASCADE
  engagement_id      UUID  NOT NULL  FK engagements(id)  ON DELETE CASCADE
  edge_type          TEXT  NOT NULL                            -- belongs_to | depends_on | ...
  from_node_id       UUID  NOT NULL  FK matrix_nodes(id) ON DELETE CASCADE
  to_node_id         UUID  NOT NULL  FK matrix_nodes(id) ON DELETE CASCADE
  attributes         JSONB NOT NULL DEFAULT '{}'
  evidence_event_ids UUID[] NOT NULL DEFAULT '{}'
  created_at         TIMESTAMPTZ NOT NULL DEFAULT now()
  updated_at         TIMESTAMPTZ NOT NULL DEFAULT now()
```

`matrix_nodes` and `matrix_edges` are **mutable** (support `UPDATE`) — like `identity_nodes` and `solidified_learnings`, and unlike the append-only `canonical_memory_events`. The append-only narrative lives at the *event* layer; the matrix is the current derived view.

---

## 5. Conventions decision — RLS, UUIDs, the grain fix

The repo has two divergent conventions:

- **Canonical-memory tables** (`canonical_memory_events`, identity, learnings): `deployai_uuid_v7()` IDs, **RLS policies** (`tenant_rls_<table>`, `FORCE ROW LEVEL SECURITY`) via `TenantScopedSession`.
- **Engagement tables** (`engagements`, `engagement_members`, …, migrations 0016–0019): `gen_random_uuid()` IDs, **app-layer tenant filtering**, no RLS.

**Decision (revised during 5.2a implementation): the matrix tables use `deployai_uuid_v7()` IDs but app-layer tenant + engagement filtering — *not* RLS.** The 5.1 draft had proposed RLS for consistency with canonical memory; building 5.2 showed that to be the wrong trade. The matrix tables are reached through the **internal-key control-plane API**, exactly like `engagements`, `engagement_members`, and the strategist queues — none of which use RLS. RLS depends on `TenantScopedSession` setting `app.current_tenant`; the entire engagement internal API uses a plain session. Adopting RLS would force `TenantScopedSession` into a code path that does not use it and make the matrix tables the lone RLS'd table behind the internal API. The `deployai_uuid_v7()` ID convention is kept — it is harmless and consistent with the substrate the matrix sits in.

### 5.1 The grain fix (absorbs deferred increment 1.3)

Canonical-memory tables are **tenant-grained** — they predate the engagement entity. For the matrix to be engagement-scoped, increment 5.2a adds a **nullable `engagement_id`** (the expand step, `# expand-contract: expand`, migration `0021`) to:

`canonical_memory_events`, `identity_nodes`, `identity_attribute_history`, `identity_supersessions`, `solidified_learnings`, `learning_lifecycle_states`, `tombstones`.

The column is nullable (these tables predate engagements and carry fixture rows; the `NOT NULL` flip is deferred until writers populate it) and has **no foreign key** — uniform across all seven tables. `canonical_memory_events` is append-only: an `ON DELETE CASCADE`/`SET NULL` would mutate event rows and trip the `canonical_memory_events_append_only` trigger. No-FK matches the `tombstones.original_node_id` precedent. The **new** `matrix_nodes` / `matrix_edges` tables carry `engagement_id NOT NULL` with a real FK from creation. This is the long-deferred Phase 1 increment 3, done as part of the matrix model.

---

## 6. Extension seam

DeployAI is sold as a base adopting teams' engineers tailor. The seam is built into the model, not bolted on:

- **`node_type` and `edge_type` are `TEXT`; type-specific data is JSONB `attributes`.** A new entity or relationship type is **data, not schema** — adding one needs *no migration*.
- A **type catalog** defines the known types and the attribute keys each expects — used for validation and for UI rendering. 5.1 fixes that the catalog *exists*; whether it is a code constant or a `matrix_type_catalog` table is a 5.2 call. A team customizes DeployAI by adding catalog entries (and, if they want bespoke surfaces, their own views over the generic graph).
- The graph tables never change shape when a type is added — that is the point of the property-graph choice over per-entity tables.

This is a *seam*, not a plugin system: 5.x does not build runtime extensibility tooling. It guarantees that customization does not require forking the schema.

---

## 7. Superseding the journal

`engagement_log_entries` (Phase 3) is superseded by the matrix. **No data migration is required** — the table has no production rows (DeployAI has no users). Conceptual mapping for the capture form (increment 5.4):

| Journal `entry_kind` | Becomes |
| --- | --- |
| `meeting` | a `canonical_memory_events` interaction (`event_type = meeting_note`) |
| `decision` | a `decision` matrix node |
| `risk` | a `risk` matrix node |
| `next_action` | a `commitment` matrix node |

`engagement_log_entries` is retired in **increment 5.4** — not before. The Phase 4 engagement detail page and capture form read the journal today; the table and its API are dropped only once 5.3 (map view) and 5.4 (structured capture) have repointed those surfaces. Increments 5.2a/5.2b leave the journal untouched and working in parallel.

---

## 8. Increment plan (Phase 5)

| # | Increment | Builds |
| --- | --- | --- |
| 5.1 | **This document.** | The model, decided. |
| 5.2a | Matrix schema, grain fix & domain models | Migrations `0020` (`matrix_nodes`, `matrix_edges`) + `0021` (`engagement_id` grain fix), domain models. |
| 5.2b | Matrix control-plane API | Internal CRUD API for matrix nodes & edges. |
| 5.3 | Matrix BFF & map view | BFF routes + a map view on the engagement detail page. |
| 5.4 | Structured capture & journal retirement | Manual entry writes structured nodes/events (the `EngagementCaptureForm` evolves — the Phase 6 manual-entry harness); `engagement_log_entries` and its API are retired. |

---

## 9. Open questions — carried into 5.2b+

- **Type catalog: table or constant?** Start with a constant; promote to a `matrix_type_catalog` table if/when teams need per-tenant custom types. 5.2b's CRUD API validates `node_type` / `edge_type` against the catalog.
- **`NOT NULL` flip for `engagement_id`** on canonical-memory tables — deferred (no production data), as with the strategist-queue `engagement_id`.
- **Edge cardinality / uniqueness constraints** (e.g. one `belongs_to` per stakeholder) — left to 5.2b, per edge type.

**Resolved during 5.2a:** RLS on the matrix tables — *not* adopted; the matrix uses app-layer tenant/engagement filtering like the other internal-API tables (see §5). The grain-fix migration carries the `# expand-contract: expand` marker (it adds columns to canonical-memory tables).
