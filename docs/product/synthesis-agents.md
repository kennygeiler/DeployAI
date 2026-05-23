# DeployAI — Synthesis agents (Oracle + Master Strategist)

| | |
| --- | --- |
| **Status** | Design / decision record. Phase 7 increment **7.1**. |
| **Date** | 2026-05-23 |
| **Drives** | Increments 7.2 (Oracle + CP `/insights` endpoint), 7.3 (BFF + UI surface), 7.4 (Master Strategist cross-engagement insights). |
| **Roadmap** | [`deployai-source-of-truth-spec.md`](./deployai-source-of-truth-spec.md) §16 — Phase 7. |
| **Builds on** | [`deployment-matrix-model.md`](./deployment-matrix-model.md) — the matrix property graph; [`matrix-extraction-agent.md`](./matrix-extraction-agent.md) — the Cartographer extraction pattern this design re-uses. |

This document is the **decision record** for the synthesis layer that reads the matrix and produces cross-team insight, suggestions, learnings, and opportunity detection. It is increment 7.1's deliverable: it does not ship code. Increments 7.2–7.4 build the agents from it.

---

## 1. Why — the loop in one paragraph

Phase 5 built the deployment matrix; Phase 6 fed it. **What's missing is the payoff** — the agent layer that reads the populated matrix + recent canonical events and tells the cross-functional team *what to do about it*. A stale commitment, an unanswered risk, a decision with no owner, a stakeholder going silent — these are observable from the graph but no one on the team has the time to scan for them across 5+ deployments. Phase 7 ships two agents: **Oracle** reads one engagement's matrix and emits per-engagement insights; **Master Strategist** reads the whole portfolio and emits cross-engagement insights. Both surface on the UI with refresh + dismiss. Neither mutates the matrix — insights are *observations*, not graph edits.

This is the *synthesis* layer. **Distinct from Phase 6 extraction.** Extraction (Cartographer) turns prose into matrix nodes/edges. Synthesis (Oracle / Master Strategist) turns matrix nodes/edges into insights. Different prompts, different storage, different UI surface, both share the same `LLMProvider` injection pattern.

---

## 2. The two agents

| Agent | Scope | Reads | Emits | Trigger |
| --- | --- | --- | --- | --- |
| **Oracle** | One engagement | matrix nodes + edges + last N canonical events for that engagement | per-engagement insights (commitment / risk / decision / stakeholder) | "Refresh insights" button on engagement detail page |
| **Master Strategist** | One tenant (whole portfolio) | matrix nodes + edges across all of the tenant's engagements; engagement metadata; member roster | cross-engagement insights (recurring risk / vendor concentration / role-coverage gap) | "Refresh portfolio insights" button on `/engagements` portfolio page |

Same Python module shape: a pure function (no FastAPI, no SQLAlchemy) that takes domain dataclasses + an `LLMProvider`, returns `InsightDraft` objects. The CP route handler composes the I/O.

---

## 3. Insight types — per-engagement (Oracle, MVP)

Each insight type has (a) a **trigger rule** — a deterministic predicate the agent uses to decide if there is anything to ask the LLM about, and (b) a **prompt cue** — the matrix slice handed to the LLM so it can write the narrative `title` + `body` with citations.

Oracle runs the four predicates locally, builds a candidate list, then asks the LLM in **one** call to write the human-facing narrative for each candidate. Deterministic gating + LLM phrasing — cheap, predictable, doesn't hallucinate categories that don't exist.

| Type | Predicate (deterministic) | Prompt cue | Severity |
| --- | --- | --- | --- |
| **`stale_commitment`** | `commitment` node with no canonical event citing it in the last 14 days (configurable) | the commitment node + its evidence events | `medium` if 14–30d, `high` if >30d |
| **`unanswered_risk`** | `risk` node with no outgoing `blocks` or `affects` edge to a `commitment` / `decision` | the risk node + the matrix neighborhood | `medium` if no events in 7d, `high` if no events in 21d |
| **`decision_without_owner`** | `decision` node with no incoming `sponsors` or `owned_by` edge from a `stakeholder` | the decision node + nearby stakeholders | `medium` always |
| **`stakeholder_neglect`** | `stakeholder` node marked as sponsor (attribute `is_sponsor=true`, or the *first* stakeholder per engagement as a fallback) with no canonical events authored-by or mentioning them in the last 14 days | the stakeholder + their last interaction | `low` if 14–30d, `medium` if >30d |

**Note on `owned_by`:** the current matrix edge catalog (matrix.py) ships `owned_by` *not* in the canonical list — see open question §15. The predicate uses `sponsors` as the primary owner relation, `owns` as fallback.

---

## 4. Insight types — cross-engagement (Master Strategist, MVP)

Tenant-scoped predicates over the union of all engagements:

| Type | Predicate (deterministic) | Prompt cue | Severity |
| --- | --- | --- | --- |
| **`recurring_risk_pattern`** | Same risk *title family* (Jaccard ≥ 0.6 on tokenized title) appears on ≥ 2 engagements | the risk titles + engagement names + each engagement's matched citation events | `medium` if 2, `high` if 3+ |
| **`system_concentration`** | Same `system` node title appears on ≥ 3 engagements (Jaccard ≥ 0.7) | the system + the engagements it spans + edges around it | `medium` if 3, `high` if 5+ |
| **`role_coverage_gap`** | Engagement with `status='active'` that has no member with role `fde` *or* `biz_dev` while ≥ 50% of the tenant's active engagements do | the engagement + the tenant's role-coverage histogram | `medium` always |

Same architecture: deterministic predicates → one LLM call to phrase the narrative.

**Cost guardrail:** per-tenant snapshot capped at 200 nodes + 400 edges + 5 engagements' worth of events. If the portfolio is bigger, the predicate runs but the LLM context truncates to the top N by recency (open question §15).

---

## 5. LLM injection

Same pattern as `matrix_extractor`. **Reuse the existing `LLMProvider` Protocol** from `packages/llm-provider-py`.

- **Production:** `AnthropicProvider`
- **Dev fallback:** `create_stub_provider()` — returns deterministic strings (insight body = `"stub insight for <type>"`); the predicates still fire correctly, only the narrative is canned.
- **Tests:** per-test `vi.fn`-style fake injected via `app.dependency_overrides[get_llm_provider]`. Same `get_llm_provider()` factory already in `control_plane/agents/llm.py` — 7.2 imports it, no new factory.
- **Async note:** `chat_complete` is sync; wrap in `await asyncio.to_thread(...)` in the route handler.

---

## 6. Trigger model

**Decision: on-demand only for MVP.** No nightly batch, no chained refresh after `/ingest`.

- **Per-engagement Oracle:** "Refresh insights" button on the engagement detail page → POST to `/internal/v1/engagements/{id}/insights/refresh` → sync run → returns the new insight list.
- **Per-tenant Master Strategist:** "Refresh portfolio insights" button on `/engagements` portfolio page → POST to `/internal/v1/tenants/{tenant}/insights/refresh` → sync run → returns the new insight list.

Why on-demand: keeps the loop visible (you click → it runs → you see new insights); no background workers required; cost per refresh is **one** LLM call regardless of how many candidates the predicates produced (predicates run locally, LLM only phrases). Each refresh costs ~$0.05 / engagement, ~$0.15 / tenant.

A nightly refresh + chained refresh on `/ingest` are obvious follow-ups; deferred to keep MVP plumbing thin.

---

## 7. Storage — the `matrix_insights` table

One table for both per-engagement and cross-engagement insights. `engagement_id` is nullable; null = tenant-scoped (Master Strategist).

| Column | Type | Notes |
| --- | --- | --- |
| `id` | `uuid` (v7 via `deployai_uuid_v7()`) | PK |
| `tenant_id` | `uuid` NOT NULL | always |
| `engagement_id` | `uuid` | nullable; null = tenant-scoped insight; FK with `ON DELETE CASCADE` |
| `agent` | `text` NOT NULL CHECK | `'oracle'` \| `'master_strategist'` |
| `insight_type` | `text` NOT NULL | one of the type slugs in §3 / §4 |
| `severity` | `text` NOT NULL CHECK | `'low'` \| `'medium'` \| `'high'` |
| `title` | `text` NOT NULL | short narrative title (LLM-written) |
| `body` | `text` NOT NULL | longer narrative (LLM-written, ≤ 1 000 chars) |
| `citation_node_ids` | `uuid[]` | matrix node ids the insight is about |
| `citation_edge_ids` | `uuid[]` | matrix edge ids the insight is about |
| `citation_event_ids` | `uuid[]` | canonical event ids cited |
| `dedup_key` | `text` | deterministic key for idempotency (see §9) |
| `status` | `text` NOT NULL DEFAULT `'open'` CHECK | `'open'` \| `'dismissed'` \| `'resolved'` |
| `created_at` | `timestamptz` NOT NULL default `now()` | |
| `decided_at` | `timestamptz` | null until dismissed/resolved |
| `decided_by` | `text` | optional actor id |

Indexes: `(tenant_id, engagement_id, status)`, `(tenant_id, agent, status)`, `(dedup_key)` UNIQUE.

Migration `0024_matrix_insights.py` (7.2 ships it).

---

## 8. Prompt shape — Oracle (per-engagement)

System prompt — single shape for all per-engagement types:

```
You are the Oracle for DeployAI. You read a deployment's matrix and a list
of candidate observations the system has flagged, and write a short
narrative for each one suitable for a human deployment strategist.

Return a JSON array. One element per candidate, in the same order:

  { "title": string (≤ 100 chars, plain language, no jargon),
    "body":  string (≤ 600 chars, what's happening + why it matters + 1
                     concrete next step) }

Rules:
- Be specific. Name the stakeholder, the commitment, the risk. Do not
  generalize.
- Cite by name, not by id. Ids are for the system; humans read names.
- If a candidate is actually fine on second look (the data is misleading),
  set title="" and the row will be dropped.
- Output ONLY the JSON array. No prose, no code fences.
```

User prompt — the candidate list + matrix context:

```
Engagement: <name> (phase: <phase>)
Matrix summary:
- N stakeholders, N organizations, N systems, N decisions, N risks,
  N commitments, N opportunities
- Top edges: <top-10 edges by type counts>

Candidates flagged for narrative:
[1] type=stale_commitment severity=high
    commitment.title = "..."
    days_since_last_event = 42
    evidence_events = ["...", "..."]
[2] type=unanswered_risk severity=medium
    risk.title = "..."
    neighborhood_edges = ["...", "..."]
[3] ...
```

One LLM call, N candidates returned. Skipped candidates (empty title) are dropped.

---

## 9. Prompt shape — Master Strategist (cross-engagement)

Same return-array structure as Oracle. User prompt adds engagement-name + per-candidate engagement list:

```
Tenant: <name>
Portfolio summary:
- N engagements active, M paused, K complete
- Role coverage: fde present in X/N, biz_dev in Y/N, strategist in Z/N
- Risk title-family counts (top 10)
- System title-family counts (top 10)

Candidates flagged for narrative:
[1] type=recurring_risk_pattern severity=high
    risk_title_family = "vendor data residency"
    engagements = ["Acme County", "Travis County", "Polk County"]
    citation_events = [{eng: "Acme County", title: "..."}, ...]
[2] ...
```

System prompt identical to Oracle's except "Oracle" → "Master Strategist for DeployAI."

---

## 10. Response parsing & validation

Per insight:

1. **Strict JSON parse.** Parse failure → log + return zero insights for this run (best-effort, like Cartographer).
2. **Title check.** Empty string = LLM dropped the candidate, skip it.
3. **Severity & type from the predicate, not the LLM** — the LLM only writes title/body. Type and severity come from the deterministic predicate that flagged the candidate.
4. **Length truncation.** `title` ≤ 100 chars, `body` ≤ 600 chars (truncate with ellipsis).
5. **Persist** as `matrix_insights` rows with status='open', `dedup_key` set per §11.
6. **Idempotent commit** — see §11. If `dedup_key` collides with an existing row, update the title/body in place, leave status untouched.

---

## 11. Idempotency

**The `dedup_key` makes refresh idempotent.** Each candidate has a deterministic key built from its inputs:

- Per-engagement: `oracle:<engagement_id>:<insight_type>:<sorted_citation_node_ids>`
- Per-tenant: `master_strategist:<tenant_id>:<insight_type>:<sorted_engagement_ids>:<sorted_citation_node_ids>`

On refresh:
1. Predicates run → candidate list with `dedup_key`s computed.
2. For each candidate, upsert by `dedup_key`:
   - If an `open` row exists → update title/body/severity, leave status untouched.
   - If a `dismissed` row exists → **skip** (the user already triaged it; don't re-surface unless it changes shape, which would change the dedup_key).
   - If a `resolved` row exists → re-open it and update fields (the underlying problem came back).
3. Open rows whose `dedup_key` is NOT in the new candidate list → mark `auto_resolved` and set status='resolved' (the predicate no longer flags this — the team fixed it, treat the insight as closed).

This means **refresh is free of duplicate noise** and the user's dismissal sticks. Cost guardrail: a refresh that produces the same candidates as last time spends one LLM call only because the predicates require LLM-written narrative for new/changed candidates; if every dedup_key already has an open row with up-to-date title/body, we skip the LLM call entirely (predicate compares input hashes).

---

## 12. Code location

```
services/control-plane/src/control_plane/agents/
├── llm.py                  # existing — get_llm_provider() factory, reused
├── matrix_extractor.py     # existing — Cartographer
├── oracle.py               # NEW — Oracle pure function
└── master_strategist.py    # NEW — Master Strategist pure function

services/control-plane/src/control_plane/domain/canonical_memory/
└── insights.py             # NEW — MatrixInsight ORM model

services/control-plane/src/control_plane/api/routes/
└── engagements_internal.py # ADD — per-engagement /insights routes
└── tenants_internal.py     # NEW — per-tenant /insights routes
```

Each agent module is a **pure function**: `run_oracle(*, engagement_id, nodes, edges, recent_events, llm) -> list[InsightDraft]`. No I/O, no DB, no FastAPI. The route handler composes the I/O: load matrix → run predicates → call agent → upsert by dedup_key.

---

## 13. Guardrails

- **Snapshot caps** — Oracle: ≤ 200 nodes, ≤ 400 edges, ≤ 50 recent events. Master Strategist: ≤ 5 engagements × 200 nodes each, ≤ 1000 edges total. If exceeded, truncate by recency and log.
- **LLM input cap** — total prompt ≤ 12 000 chars; truncate the candidate list (drop lowest-severity first).
- **Output tokens** — 3 000 max.
- **Temperature** — 0.0 (deterministic for replays + tests).
- **LLM errors** — caught, return zero insights, log; refresh is best-effort like Cartographer.
- **No retries** — failure surfaces as "Refresh failed — try again" in the UI.
- **Predicate-only re-runs** — if dedup_keys all hit existing open rows with matching input hashes, **skip the LLM call entirely** (cost: $0). Predicate run is always free.

---

## 14. UI surface

**Per-engagement:** a new "Insights" section on the engagement detail page, above the deployment matrix, below the engagement header. Empty state: "No insights yet — click refresh." Populated: a list of cards, each with severity chip, title, body, citation links (clickable node/event ids that scroll into the matrix view), and two buttons: `Dismiss` (sets status=dismissed) and `Resolve` (sets status=resolved). A `Refresh` button at the top of the section.

**Per-tenant:** a new "Portfolio insights" section at the top of `/engagements` (above the engagement list). Same card shape; cards link out to the specific engagement(s) the insight cites.

Both surfaces fetch a list endpoint (`GET …/insights?status=open`) on mount and re-fetch after refresh. No streaming, no SSE — refresh is sync POST returns the list.

---

## 15. Open questions — carried into 7.2/7.3/7.4

- **`owned_by` edge type.** The decision_without_owner predicate wants a clear "this person owns this decision" edge. Current matrix.py ships `sponsors` and `owns` but not `owned_by`. 7.2 decision: predicate uses `sponsors` primary, `owns` fallback. If extraction quality suggests `owned_by` should be added to the catalog, do it in a focused matrix-catalog increment, not in 7.2.
- **Stakeholder `is_sponsor` attribute.** The stakeholder_neglect predicate needs a way to identify the deal sponsor. Cartographer doesn't yet set attributes on nodes. 7.2 fallback: treat the *first* stakeholder created on an engagement as the de facto sponsor. Better answer: a `mark as sponsor` action on the UI in a later polish increment.
- **Master Strategist snapshot cost.** A tenant with 50 engagements is bigger than the snapshot caps. 7.4: cap to top 5 by activity (recent event count), log truncation. Real tenant-wide synthesis is v2.
- **Insight expiry.** Open insights never auto-close on time alone — only via predicate re-runs (§11 auto_resolved) or user action. Reasonable for MVP; revisit if open lists grow stale.
- **Two-level insights.** A cross-engagement insight that says "system X concentration is high" implies per-engagement work to harden the dependency. 7.4 keeps them as separate cards; a "child insights" / "parent insight" relationship can come later.
- **Title-family Jaccard threshold.** §4 picks 0.6/0.7. Likely needs tuning against real data. Make it a constant in the module; revisit after the first seeded portfolio run.

---

## 16. Increment plan (the implementation)

| Increment | What | Ships |
| --- | --- | --- |
| **7.2** | `migrations/0024_matrix_insights.py` + `MatrixInsight` ORM + `oracle.py` pure fn + `get_llm_provider()` reuse + per-engagement CP routes (`GET /internal/v1/engagements/{id}/insights`, `POST .../insights/refresh`, `POST .../insights/{id}/dismiss`, `POST .../insights/{id}/resolve`). Unit tests for `oracle.py` with a fake LLM; integration tests for the routes with dependency override. | Real CP API. No UI yet. |
| **7.3** | Web BFF + types (`InsightRead` shape) + `insights-cp.ts` client + BFF routes (`GET /api/bff/engagements/:id/insights`, `POST .../insights/refresh`, `POST .../insights/:insightId/dismiss` `/resolve`). `EngagementInsights.client.tsx` component on the engagement detail page above the matrix. Tests w/ MSW. | UI loop closed for per-engagement. |
| **7.4** | `master_strategist.py` pure fn + per-tenant CP routes + BFF + `PortfolioInsights.client.tsx` on `/engagements`. Tests at every layer. | Cross-engagement insight loop closed. |
