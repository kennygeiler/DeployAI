# Timeline Ledger + Intelligence Layer — design + implementation plan

**Status**: Design — not yet implemented.
**Scope**: Phase F. Spans 4 implementation bundles (F1-F4) over ~4 sprints.
**Owner**: TBD.

---

## 1. Why this exists

DeployAI today stores a **current** view of each engagement: the matrix as
it stands, the latest insights, the open proposals. It does not let a
strategist (or a future LLM) ask:

- "How did this engagement get here?"
- "When did this risk first appear, and which conversation triggered it?"
- "What changed in the last 30 days, and who/what caused it?"
- "If we backtest a year of data, what would the matrix have looked like
  at each milestone?"
- "Which AI-generated proposals were rejected, and why? Is the extractor
  getting worse over time?"
- "What patterns repeat across engagements that closed-lost?"

The data needed to answer these is already in the system, but it's
scattered across `email_ingest_events`, `meeting_webhook_events`,
`matrix_proposals` (with state transitions), `matrix_nodes.evidence_event_ids`,
`strategist_activity_events`, audit emits, and oracle insight rows. The
ledger consolidates them into one append-only causal graph + ships four
surfaces + an intelligence layer that derives temporal insights.

**Strategic framing**: stops selling "extraction", starts selling
"institutional memory + causal-trace audit + temporal intelligence."
Differentiated against Notion (no causality) + Gong (no engagement-level
unit-of-analysis) + DIY internal tools (no audit posture).

---

## 2. Concepts

### 2.1 Event
An immutable, timestamped record of something that happened in or to an
engagement. Every existing surface that emits an audit row also emits a
ledger event (via a dual-emit helper). Backfilled from existing tables.

### 2.2 Causal edge
Each event optionally points at the events that *caused* it (`caused_by`)
and the matrix entities it *affected* (`affected`). This turns the linear
event stream into a directed acyclic graph (DAG) over time.

### 2.3 Snapshot
A reconstructed view of matrix state at a chosen `as_of` timestamp.
Powered by replaying events from epoch (or, eventually, from the nearest
materialized snapshot).

### 2.4 Insight (temporal)
A derived statement about velocity, drift, or pattern. Distinct from the
existing per-engagement Oracle insights, which are statements about the
*current* matrix. Temporal insights live in their own table with a
typed `kind`, severity, time window, and supporting evidence (pointers
back to ledger events).

---

## 3. Data model

### 3.1 Migration 0034 — `ledger_events`

```sql
CREATE TABLE ledger_events (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id    UUID NOT NULL REFERENCES app_tenants(id),
  engagement_id UUID NULL REFERENCES engagements(id), -- NULL for tenant-wide events
  occurred_at  TIMESTAMPTZ NOT NULL,            -- real event time (not insertion)
  recorded_at  TIMESTAMPTZ NOT NULL DEFAULT now(), -- when the ledger row landed
  actor_kind   VARCHAR(40) NOT NULL,            -- 'user' | 'system' | 'agent:<name>'
  actor_id     VARCHAR(200) NULL,               -- UUID for user, name for agent
  source_kind  VARCHAR(80) NOT NULL,            -- see enum below
  source_ref   UUID NULL,                       -- pointer into origin table
  summary      TEXT NOT NULL,                   -- human readable, ≤500 chars
  detail       JSONB NOT NULL DEFAULT '{}',     -- structured (NO secrets)
  CONSTRAINT ledger_summary_len CHECK (char_length(summary) BETWEEN 1 AND 500)
);

CREATE INDEX ix_ledger_tenant_occurred ON ledger_events (tenant_id, occurred_at DESC);
CREATE INDEX ix_ledger_engagement_occurred ON ledger_events (engagement_id, occurred_at DESC) WHERE engagement_id IS NOT NULL;
CREATE INDEX ix_ledger_source_kind ON ledger_events (source_kind);
CREATE INDEX ix_ledger_actor ON ledger_events (actor_kind, actor_id);
CREATE INDEX ix_ledger_detail_gin ON ledger_events USING GIN (detail jsonb_path_ops);
```

**source_kind enum** (extensible; document additions in the same migration):
```
email_ingest             meeting_webhook         manual_capture
llm_proposal_created     proposal_accepted       proposal_rejected
matrix_node_created      matrix_node_updated     matrix_node_deleted
matrix_edge_created      matrix_edge_deleted
insight_opened           insight_closed
recommendation_emitted   recommendation_actioned
engagement_phase_change  member_added            member_removed
settings_change          audit_other
```

### 3.2 Migration 0035 — `ledger_event_causes`

Many-to-many causality. Separate table (not jsonb array) so we can index
both directions efficiently.

```sql
CREATE TABLE ledger_event_causes (
  event_id        UUID NOT NULL REFERENCES ledger_events(id) ON DELETE CASCADE,
  caused_by_id    UUID NOT NULL REFERENCES ledger_events(id) ON DELETE CASCADE,
  PRIMARY KEY (event_id, caused_by_id),
  CHECK (event_id != caused_by_id)
);

CREATE INDEX ix_ledger_cause_forward ON ledger_event_causes (event_id);
CREATE INDEX ix_ledger_cause_reverse ON ledger_event_causes (caused_by_id);
```

### 3.3 Migration 0036 — `ledger_event_affects`

What matrix entities this event touched. Polymorphic (node | edge |
insight | recommendation).

```sql
CREATE TABLE ledger_event_affects (
  event_id     UUID NOT NULL REFERENCES ledger_events(id) ON DELETE CASCADE,
  entity_kind  VARCHAR(40) NOT NULL,  -- 'matrix_node' | 'matrix_edge' | 'insight' | 'recommendation'
  entity_id    UUID NOT NULL,
  PRIMARY KEY (event_id, entity_kind, entity_id)
);

CREATE INDEX ix_ledger_affects_entity ON ledger_event_affects (entity_kind, entity_id);
```

### 3.4 Migration 0037 — `temporal_insights`

Derived insights computed by the intelligence layer. Distinct table from
existing `engagement_insights` (Oracle output) to keep grain-of-truth
clear: oracle = current-state, temporal = time-window-derived.

```sql
CREATE TABLE temporal_insights (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id      UUID NOT NULL REFERENCES app_tenants(id),
  engagement_id  UUID NULL REFERENCES engagements(id), -- NULL = cross-engagement
  insight_kind   VARCHAR(80) NOT NULL,                  -- see catalog §5
  severity       VARCHAR(16) NOT NULL,                  -- 'info' | 'low' | 'medium' | 'high' | 'critical'
  title          VARCHAR(200) NOT NULL,
  narrative      TEXT NOT NULL,                          -- markdown, ≤4000 chars
  window_start   TIMESTAMPTZ NOT NULL,
  window_end     TIMESTAMPTZ NOT NULL,
  evidence_event_ids UUID[] NOT NULL DEFAULT '{}',       -- pointers into ledger_events
  metrics        JSONB NOT NULL DEFAULT '{}',            -- structured numbers backing the insight
  status         VARCHAR(16) NOT NULL DEFAULT 'open',    -- 'open' | 'acknowledged' | 'dismissed' | 'resolved'
  acknowledged_by UUID NULL,
  acknowledged_at TIMESTAMPTZ NULL,
  created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
  CHECK (window_end >= window_start),
  CHECK (severity IN ('info','low','medium','high','critical')),
  CHECK (status IN ('open','acknowledged','dismissed','resolved'))
);

CREATE INDEX ix_temporal_tenant_engagement ON temporal_insights (tenant_id, engagement_id, status, severity);
CREATE INDEX ix_temporal_kind ON temporal_insights (insight_kind);
CREATE INDEX ix_temporal_window ON temporal_insights (window_start, window_end);
```

### 3.5 Migration 0038 — `matrix_snapshots` (deferred to Phase F3)

Materialized matrix state at coarse time intervals (daily) for fast
"matrix as of" queries. Optional optimization — Phase F1/F2 ship with
replay-from-epoch (slow but correct).

```sql
CREATE TABLE matrix_snapshots (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  engagement_id  UUID NOT NULL REFERENCES engagements(id),
  as_of          TIMESTAMPTZ NOT NULL,
  matrix_state   JSONB NOT NULL,  -- nodes + edges array, full denormalized form
  event_id_high  UUID NOT NULL,   -- watermark — last event included
  computed_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (engagement_id, as_of)
);
```

---

## 4. Write path

### 4.1 `emit_ledger_event` helper

New module: `services/control-plane/src/control_plane/ledger/emitter.py`.

```python
async def emit_ledger_event(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    engagement_id: uuid.UUID | None,
    occurred_at: datetime,
    actor_kind: str,
    actor_id: str | None,
    source_kind: str,
    source_ref: uuid.UUID | None,
    summary: str,
    detail: dict[str, Any],
    caused_by: list[uuid.UUID] = (),
    affects: list[tuple[str, uuid.UUID]] = (),
) -> LedgerEvent:
    """Write a ledger event + cause/affect rows in one flush.

    Caller owns the commit (matches emit_audit_event semantics).
    Validates source_kind against allowed enum; raises ValueError otherwise.
    Strips secret-likely keys from `detail` defensively (api_key, signing_secret).
    """
```

### 4.2 Dual-emit from `emit_audit_event`

`emit_audit_event` (existing, PR #153) becomes a thin wrapper that also
calls `emit_ledger_event`. Existing call sites get free ledger coverage.
The audit table is preserved (UI binds to it; backward-compat).

Mapping: every audit event becomes a ledger event with:
- `source_kind` = the audit category prefix (e.g. `"audit_other"` if no
  match, else specific kind for recognized categories like
  `"break_glass.requested"` → `source_kind="audit_other"`,
  `tenant.webhook.created"` → `"settings_change"`).

The audit event's `category` + `summary` + `detail` map directly. The
ledger row's `affects` is empty unless the caller passes it.

### 4.3 New direct ledger emit sites (no audit equivalent today)

- `email_ingest_events` insert → `emit_ledger_event(source_kind="email_ingest", source_ref=event.id, affects=[])`
- `meeting_webhook_events` insert → `source_kind="meeting_webhook"`
- `matrix_proposals` insert → `source_kind="llm_proposal_created"`, `caused_by=[ingest_event_ledger_id]`
- `matrix_proposals` accept → `source_kind="proposal_accepted"`, `caused_by=[proposal_created_ledger_id]`, `affects=[(matrix_node, node_id)]`
- `matrix_proposals` reject → `source_kind="proposal_rejected"`, `caused_by=[proposal_created_ledger_id]`
- `matrix_nodes` create/update/delete → corresponding `source_kind`
- `matrix_edges` create/delete → corresponding
- `engagement_insights` open/close → `source_kind="insight_opened"|"insight_closed"`, `affects=[(insight, insight_id)]`
- Oracle / Master-Strategist runs → `source_kind="recommendation_emitted"`, `actor_kind="agent:oracle"`

### 4.4 Backfill script

`services/control-plane/src/control_plane/cli/ledger_backfill.py`:

```
python -m control_plane.cli.ledger_backfill --tenant-id <uuid> [--dry-run]
```

Reads the source tables in order, writes ledger rows + cause/affect
edges. Idempotent: uses `source_ref` as a uniqueness key to skip
already-backfilled events. Outputs counts per source_kind.

### 4.5 Transaction discipline

`emit_ledger_event` does `session.add` + `flush` only; caller commits.
This matches the existing `emit_audit_event` contract and keeps the
ledger write inside the same transaction as the originating state change
(so a rollback drops both, never leaking phantom ledger rows).

---

## 5. Intelligence layer — temporal insight catalog

The intelligence layer is a set of `analyzer` functions, each owning one
`insight_kind`. Analyzers read the ledger + matrix tables and write rows
into `temporal_insights`. They run on a schedule (cron) per tenant.

### 5.1 Analyzer interface

`services/control-plane/src/control_plane/intelligence/base.py`:

```python
class Analyzer(Protocol):
    insight_kind: str
    default_window: timedelta

    async def run(
        self,
        session: AsyncSession,
        *,
        tenant_id: uuid.UUID,
        engagement_id: uuid.UUID | None,
        window_start: datetime,
        window_end: datetime,
    ) -> list[TemporalInsightWrite]:
        ...
```

Analyzers are pure: input window → output insights. Idempotent: re-running
the same window should produce stable insight IDs (use deterministic
hash of window + kind + engagement_id when generating the natural key
that prevents duplicates).

### 5.2 Built-in analyzers (Phase F1 ships 4; F4 ships the rest)

#### Velocity analyzers (statistical, no LLM)

1. **`stakeholder_churn`** — count `member_removed` + `matrix_node_deleted(node_type=stakeholder)` events in window vs prior window. Fire if churn rate > 2x prior period. Severity scales with rate.

2. **`decision_cycle_slowdown`** — for each decision node, compute `created_at` → `accepted_at` (proposal lifecycle). Compare current 30d mean to prior 30d mean. Fire if slowdown > 50%.

3. **`risk_open_rate`** — risks opened minus risks closed in window. Fire if net new risks > N (configurable per tenant).

4. **`engagement_silence`** — no ledger events for engagement in last 14 days. Fire info-level.

#### Quality analyzers (statistical)

5. **`extractor_acceptance_drift`** — for each `actor_kind="agent:matrix_extractor"`, compute proposal acceptance rate by week. Fire if drop > 20 percentage points week-over-week. Critical signal of prompt regression or transcript-format change.

6. **`workload_concentration`** — % of `proposal_accepted` + `proposal_rejected` events authored by a single actor over 30 days. Fire if > 70% — sole-reviewer risk.

#### Pattern analyzers (LLM-assisted)

7. **`recurring_failure_pattern`** — cross-engagement. For engagements where a specific risk node was opened then a specific decision node was created within 14 days, see if other engagements have the leading risk but not yet the decision. Output: "Engagement X shows the same leading pattern as engagements Y and Z (which then…)." Requires LLM to summarize the pattern in human terms.

8. **`pre_mortem_signals`** — for an open engagement, compare its 30d event distribution to engagements that have a recorded "closed-lost" or "closed-stalled" outcome (Phase F4 — need outcome labelling first). Surface leading indicators.

#### Causal analyzers (LLM-assisted)

9. **`decision_provenance_summary`** — for any matrix decision node, walk the causal chain backward and ask the LLM to produce a 1-paragraph "why does this decision exist" narrative. Stored alongside the decision, refreshed when new caused_by edges land.

10. **`post_mortem_narrative`** — on request, generate a markdown timeline narrative for an engagement window. Inputs: ledger events in window + matrix snapshots at boundaries. Output: structured markdown with sections (timeline, who did what, AI proposal acceptance rate, decisions made, risks opened/closed, lessons).

### 5.3 Analyzer scheduler

`services/control-plane/src/control_plane/intelligence/scheduler.py`:

- Per-tenant cron: every analyzer runs hourly for engagement-scoped, daily for tenant-scoped.
- Driven by a new `make analyze` target + a background worker (or, simpler v1: a `/internal/v1/intelligence/run` endpoint called by an external cron).
- Each run is bounded: ≤30s per analyzer; logs to JSON; emits `analyzer_run` ledger events so the system audits itself.

### 5.4 Insight delivery

- New web surface: `/engagements/{id}/insights/temporal` — table view of open temporal insights, filterable by kind + severity.
- Cross-engagement surface: `/portfolio/insights` — same table at tenant grain.
- Each insight expandable to show: window, metrics JSON, evidence event list (clickable into the timeline).
- Acknowledge / dismiss / resolve actions emit audit + ledger events.
- High-severity insights also push a webhook (existing webhook system, new event_type `temporal.insight.high`).

---

## 6. Read APIs

All under `services/control-plane/src/control_plane/api/routes/ledger_internal.py`:

```
GET  /internal/v1/engagements/{id}/ledger
  ?from=<iso>&to=<iso>
  &source_kind=<kind>[,kind...]
  &actor_id=<uuid>
  &cursor=<opaque>
  &limit=<int, default 100, max 500>
  -> paginated chronological list

GET  /internal/v1/engagements/{id}/ledger/{event_id}
  -> single event with cause/affect arrays expanded

GET  /internal/v1/engagements/{id}/ledger/{event_id}/chain
  ?direction=backward|forward|both
  ?max_depth=<int, default 5>
  -> walk caused_by / caused_others to depth N

GET  /internal/v1/engagements/{id}/matrix-snapshot
  ?at=<iso>
  -> reconstructed matrix at point in time

POST /internal/v1/engagements/{id}/post-mortem
  body: { window_start, window_end, format: "markdown"|"json" }
  -> LLM-generated narrative

GET  /internal/v1/temporal-insights
  ?tenant_id=<uuid>&engagement_id=<uuid>
  ?status=open&severity_at_least=medium
  ?kind=<kind>
  -> list

PATCH /internal/v1/temporal-insights/{id}
  body: { status, acknowledged_by }
  -> ack/dismiss/resolve

POST /internal/v1/intelligence/run
  body: { tenant_id, engagement_id?, analyzer_kinds?, force? }
  -> trigger analyzers manually (also schedulable via cron)
```

All require `X-DeployAI-Internal-Key`. Tenant isolation: every route
validates `tenant_id` ownership before returning data.

---

## 7. Web surfaces

### 7.1 Engagement-scoped timeline — `/engagements/{id}/timeline` (Phase F1)

- Reverse-chronological scroll, virtual list (10k+ events common).
- Left rail: filter by source_kind (checkboxes), actor (autocomplete),
  date range (preset + custom).
- Each row: icon (per source_kind) + ts + actor + summary + chip-strip
  showing affected entities.
- Click row → drawer with: full detail JSON, "Caused by" list, "Caused"
  list, "Affected" list. Each link navigates within the timeline (or
  out to the affected matrix node detail page).

### 7.2 Matrix time machine — `/engagements/{id}/matrix?at=<ts>` (Phase F3)

- Existing matrix view + a time slider at top.
- Slider snaps to days (default) with optional finer-grain on hover.
- When `at` is set, header shows "Viewing matrix as of <ts>" + "Return
  to live" button.
- Backed by `matrix-snapshot` endpoint. Phase F1: replay-on-demand.
  Phase F3: precomputed daily snapshots + delta replay.

### 7.3 Provenance drawer on matrix node detail (Phase F2)

- Existing matrix node detail page gains a "Provenance" tab.
- Renders the causal chain backward from this node, depth-3 default,
  expandable to depth-10.
- Tree-of-events view (collapsible). Each leaf clickable into the
  timeline.

### 7.4 Temporal insights surface — `/engagements/{id}/insights/temporal` + `/portfolio/insights` (Phase F4)

- Table: kind + severity + window + summary + status.
- Filter rail: kind (checkboxes), severity-at-least (select),
  status (open / acknowledged / dismissed / resolved).
- Row click → detail drawer: full narrative (markdown rendered),
  metrics JSON, evidence event list (clickable into timeline).
- Action buttons: acknowledge / dismiss / resolve.

### 7.5 Post-mortem builder — `/engagements/{id}/post-mortem` (Phase F4)

- Pick window (start/end pickers).
- Hit "Generate" → calls `POST /post-mortem` → renders markdown preview.
- Export buttons: download markdown, download PDF (existing export
  packet pipeline reused), open in new tab.
- Future: edit narrative inline before export.

---

## 8. Performance + storage

### 8.1 Cardinality budget

Per-engagement steady-state estimate:
- 100 events/day during active engagement
- 365 days × 100 = ~37k events/year/engagement
- 50 engagements × 37k = ~2M events/year/tenant
- 10 tenants × 2M = 20M events/year (total)

20M rows is well within Postgres comfort range with the indexes above.

### 8.2 Query patterns + targets

| Pattern | Target |
|---|---|
| Recent timeline (last 7 days, single engagement) | <50ms p95 |
| Full timeline scroll page (100 events, indexed seek) | <80ms p95 |
| Causal chain walk (depth 5) | <200ms p95 |
| Matrix snapshot at point in time, replay from epoch (1-year engagement) | <2s p95 (degrades as engagement ages — phase F3 fixes) |
| Matrix snapshot from precomputed snapshot + delta replay (Phase F3) | <300ms p95 regardless of engagement age |

### 8.3 Storage

JSONB `detail` is the biggest cost. Estimate 500 bytes avg per row × 20M
rows/year = ~10 GB/year. Acceptable on standard postgres. Add retention
policy in Phase F4: archive ledger events older than N years to cold S3
storage (gzipped JSON files keyed by tenant+year+month).

### 8.4 Snapshot caching strategy (Phase F3)

- Materialize daily snapshots per engagement via overnight cron.
- "Matrix at any ts" = nearest-prior daily snapshot + replay of events
  between snapshot watermark and `as_of`. Bounded replay (≤1 day of
  events).
- Snapshots stored as `matrix_state JSONB` — denormalized nodes + edges
  for one engagement, copied verbatim.

---

## 9. Security envelope

1. **Tenant isolation**: every ledger read endpoint validates `tenant_id`
   from the engagement first. No cross-tenant leakage in event lookups.
2. **Detail field hygiene**: `emit_ledger_event` strips known secret-key
   names (api_key, signing_secret, webhook_url) from `detail` defensively
   before insert. Same rule as audit emit (PR #153 + #157).
3. **PII in narratives**: LLM-generated post-mortem narratives may
   reference person names. For export PDFs, add an optional `--redact`
   flag that scrubs configured PII fields.
4. **Append-only contract**: `ledger_events` is never UPDATEd or DELETEd
   in normal flow. Hard-delete only via admin tool (audit-logged). Soft-
   delete via a new `redacted_at` column (Phase F4) if a tenant requests
   GDPR erasure.
5. **Causal-graph integrity**: `ON DELETE CASCADE` on cause/affect rows
   ensures consistency if a ledger event is admin-deleted.
6. **Rate limits**: analyzer runs are bounded by tenant quota — Phase F4
   adds per-tenant LLM token budget for the LLM-assisted analyzers.

---

## 10. Out-of-scope (intentional)

- Real-time push of ledger events (SSE / WebSocket) — Phase F4+ if real
  users need it. v1 uses polling.
- Cross-tenant analyzers (e.g. "across all customers using this tool,
  here's a benchmark") — explicit privacy decision deferred to owner.
- Editable narratives — post-mortem output is markdown, edit in your
  editor of choice. v2.
- "Undo" via causal replay (rewind matrix to a prior state by
  applying inverse events) — interesting but no clear user value yet.

---

## 11. Implementation plan — 4 bundles, sized for parallel-agent execution

### Bundle F1 — foundation (parallel-4, ~1 sprint)

**F1.a — schema + ORM**
- Migrations 0034 (ledger_events), 0035 (causes), 0036 (affects), 0037 (temporal_insights).
- ORM models in `services/control-plane/src/control_plane/domain/ledger.py`.
- Backfill script `cli/ledger_backfill.py` (idempotent, dry-run flag).
- Unit tests for ORM + backfill.

**F1.b — write path**
- `control_plane/ledger/emitter.py::emit_ledger_event` helper.
- Wire dual-emit into existing `emit_audit_event` (don't break audit consumers).
- Add direct ledger emits at: ingest, webhook, proposals, matrix CRUD, insights open/close.
- Unit + integration tests covering transaction discipline.

**F1.c — read path + 4 analyzers**
- Routes: `GET /ledger`, `GET /ledger/{id}`, `GET /temporal-insights`, `PATCH /temporal-insights/{id}`.
- Pydantic response models with `from_attributes=True`.
- 4 statistical analyzers: stakeholder_churn, decision_cycle_slowdown, risk_open_rate, engagement_silence.
- Scheduler stub: `POST /intelligence/run` manual trigger; cron wiring deferred to F4.

**F1.d — web timeline surface**
- `apps/web/src/lib/internal/ledger-cp.ts` BFF client (Zod-narrowed).
- BFF routes `/api/bff/engagements/{id}/timeline` + `/api/bff/tenant/temporal-insights`.
- Page `/engagements/{id}/timeline` with filter rail + virtual scroll.
- Web tests (vitest) + a Playwright spec hitting the timeline page.

### Bundle F2 — causality + provenance (parallel-3, ~1 sprint)

**F2.a — causal-chain endpoint**
- `GET /ledger/{event_id}/chain` walking caused_by/caused_others with depth limit.
- Indexed query optimization.
- Integration tests for cycle protection.

**F2.b — extractor analyzer + provenance summary analyzer**
- `extractor_acceptance_drift` (Phase F1 listed it; defer to F2 for proper
  prompt + window tuning).
- `decision_provenance_summary` (LLM-assisted, runs on each decision
  node's caused_by chain).
- Cost guardrails: per-tenant daily LLM token budget for analyzers.

**F2.c — web provenance drawer**
- Add "Provenance" tab to matrix node detail page.
- Tree-of-events component, collapsible, depth-N expandable.
- Vitest + Playwright coverage.

### Bundle F3 — matrix time machine (parallel-3, ~1 sprint)

**F3.a — snapshot table + cron**
- Migration 0038 `matrix_snapshots`.
- Overnight cron writes daily snapshots per engagement.
- Detection of stale snapshots; backfill on demand.

**F3.b — snapshot endpoint**
- `GET /engagements/{id}/matrix-snapshot?at=<ts>` — nearest-prior snapshot + delta replay.
- Replay must be deterministic; tests cover idempotency.
- Cache snapshots in-memory per request (engagement detail page hits multiple).

**F3.c — web time slider**
- Existing matrix view gains a time slider at top.
- Snaps to days; URL state synchronized.
- "Return to live" CTA when `at` is set.

### Bundle F4 — intelligence depth + post-mortem (parallel-4, ~1 sprint)

**F4.a — remaining analyzers**
- `workload_concentration`, `recurring_failure_pattern`,
  `pre_mortem_signals`. The latter two require engagement-outcome
  labelling: extend `engagements` with `outcome` enum
  (`active`|`closed_won`|`closed_lost`|`closed_stalled`|`abandoned`) +
  Settings UI to mark.

**F4.b — post-mortem narrative**
- `POST /engagements/{id}/post-mortem` — LLM generates markdown.
- Web page `/engagements/{id}/post-mortem` with window picker +
  generate + export (markdown / PDF / JSON).
- PDF reuses existing weasyprint pipeline (D4 / inc 13.1).

**F4.c — cross-engagement insights surface**
- `/portfolio/insights` table.
- Filter by kind/severity/status across all engagements.
- Webhook hook on `temporal.insight.high` (new event type).

**F4.d — retention + GDPR**
- Add `redacted_at` column to ledger_events (Phase F4 only — soft delete).
- CLI: `python -m control_plane.cli.ledger_redact --engagement <id>` for GDPR-erasure requests.
- Cold-storage archival job (events older than N years → S3 gzip).

---

## 12. Risks + mitigations

| Risk | Mitigation |
|---|---|
| Storage growth outpaces Postgres comfort | Partition by tenant_id + month from day one; archive to cold storage in F4. |
| Causal-chain queries explode (200-node fan-out) | Default depth-3, max depth-10. UI collapses by default. Backend caps fan-out at 200 entities and flags truncation. |
| LLM-assisted analyzers burn tokens | Per-tenant daily token budget enforced before LLM call. Counter via Prometheus. |
| Backfill mismatches reality (e.g. timestamps wrong) | Backfill is idempotent + dry-run first. Counts-per-source-kind reported before commit. |
| Existing audit consumers break when dual-emit adds latency | Lazy import + fire-and-forget pattern on the ledger half. Audit row still lands synchronously. |
| Matrix snapshot replay diverges from current state | Determinism tests: replay-from-epoch must equal current state for randomly sampled engagements. |
| LLM hallucinates in post-mortem narratives | Output is clearly marked "AI-generated draft". User reviews before export. |
| Tenant isolation regression in joins | Cross-tenant fuzz CI gate (existing) extended to cover ledger routes. |

---

## 13. Success criteria (per phase)

| Phase | Ship criterion |
|---|---|
| F1 | A strategist can open `/engagements/<id>/timeline` and scroll a year of mocked events. 4 analyzers produce stable insights on the seed tenant. |
| F2 | From any matrix node, the Provenance tab renders the causal chain. `decision_provenance_summary` runs nightly. |
| F3 | Time-slider on matrix view reconstructs state at any point in the last year in <300ms p95. |
| F4 | A 90-day engagement post-mortem markdown generates in <30s; cross-engagement insights surface lists ≥1 real recurring pattern from the seed corpus. |

---

## 14. What this unlocks for sales

- **Compliance**: append-only causal ledger satisfies "audit any decision back to source evidence" requirements common in regulated buyers (healthcare, gov, finance).
- **Onboarding**: new strategist scrubs the timeline at 2x speed in their first hour.
- **Renewals**: end-of-quarter post-mortem export is a built-in QBR artifact, automated.
- **AI quality story**: `extractor_acceptance_drift` analyzer demonstrates the product self-monitors LLM quality. Differentiation vs competitors who hand-wave "we use AI."
- **Pre-mortem**: "your engagement matches 4/6 leading indicators of stalled deployments we've seen" — actionable, not vibes.

---

## 15. Next step

If approved as-is: scope Bundle F1 (parallel-4) — 4 agent briefs covering
schema/ORM, write path, read path + 4 analyzers, web timeline surface.
Migration slots 0034-0037 pre-allocated; AGENTS.md §3 file-ownership
matrix to follow when spawning.
