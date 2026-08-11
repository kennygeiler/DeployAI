# Pilot Refresh: DRM Reframe, LangGraph Deep Agent, HITL, LongScale Testing

Date: 2026-08-11. Derived from full-repo audit (5 parallel subsystem reviews at commit 41569e6).
Goal: make DeployAI testable by a small startup as a **Deal Relationship Manager (DRM)**, with a real
LangGraph agent runtime, a first-class human-in-the-loop system, and a testing framework that proves
behavior on long-horizon (multi-year, growing-corpus) deployments.

Companion audit findings (stub-vs-real, security defects) are summarized inline where they motivate a ticket.

---

## Part 1 — DRM product critique (posited first, shapes everything below)

A DRM user is an account lead / deployment lead running 3–15 live deals. Their questions:
who matters on this deal, what state is it in, what changed since I last looked, what did we promise
and when is it due, what's stalling, what should I do next — with receipts.

### Misguided / misused today

| Feature | Verdict | Why |
|---|---|---|
| Time-slider scrubbing (arbitrary-date matrix) | **Misused** | DRM question is "what changed since last touch", not "state on May 3". Slider is also hardcoded to 90 days (`MatrixTimeSlider.client.tsx:24`). Keep snapshot infra; reframe UI as **delta digest**. |
| Cartographer as standalone service | **Misguided** | Zero production callers; regex "extraction"; LLM path weaker than the regex stub. Real extraction already lives in Agent Kenny. Delete service, keep `triage.py`. |
| Two extraction paths (Kenny extraction vs cartographer) | **Misguided** | Consolidate to one path inside control-plane. |
| `packages/shared-ui` (3,658 LOC, zero prod imports) | **Dead pre-pivot layer** | Delete. Exception: ValidationQueueCard / EvidencePanel *concepts* fold into the HITL Review Inbox (Part 2). |
| 200-file golden corpus + `release-gate.yml` | **Decorative** | Random-UUID expected citations; workflow triggers on nonexistent dirs. Delete; derive ground truth from seed generators (Part 4). |
| Adversarial reviewer on every turn | **Misused (cost)** | Doubles LLM cost + latency per turn. Make it confidence-gated / async lint with escalation, configurable per tenant. |
| Meeting presence, FOIA export, wiki lint, Master Strategist branding | **Out of DRM scope** | Cut or shelve. One agent, one name: Kenny. |
| BlueState-XL 5-year scenario | **Misclassified, keep** | Not a product feature — it is the longscale test asset. Move mentally into the eval column. |
| MCP outbound connectors (5 kinds, 1 real OAuth) | **Right idea, unsafe** | SSRF hole (endpoint accepted as bare string), kill switch is a stub. Narrow to Slack until hardened. |
| `services/ingest` "service" | **Misnamed** | 141 LOC of pure helpers, no I/O. Fold into `_shared`. |

### Missing for DRM (the refresh)

1. **Delta digest** — "since your last visit / this week": new stakeholders, decisions, risks, silence. Built on existing snapshots + `temporal_insights`.
2. **Commitment tracking** — extract promises ("we'll deliver X by W22") as first-class nodes with due dates and owners; overdue = alert.
3. **Follow-ups surfaced** — snooze/follow-up BFF routes already exist with UI deliberately hidden (`EngagementInsights.client.tsx:232`). Unify the two insight models and ship the UI.
4. **Stall detection surfaced** — trailing-silence detection exists in seeds/insights; make it a front-page signal.
5. **Kenny in Slack** — answer questions with citations where the team already lives. Slack app + HMAC verification already exist inbound; add slash-command/mention → answer.
6. **Weekly digest email** — outbound email (Resend/SES); email *import* already real.
7. **CRM sync (HubSpot first)** — one-way import of companies/contacts/deals → stakeholders/engagements. Startups will not re-enter data.
8. **Capture-first UX** — the adoption risk is data entry. Lean on the already-real M365/Gmail/Slack ingest + review queue as the core loop.

---

## Part 2 — HITL design

Two HITL modes, one surface.

### A. Review Inbox (async HITL) — unifies four queues
- **Extraction proposals** (exists today as MatrixProposals) — accept/reject/bulk.
- **Agent escalations** (new) — when Kenny's confidence is low or citations fail verification twice, it declines and files an escalation. A human answers; the answer is recorded as a canonical ledger event with citations → future questions are grounded by it. This is the knowledge flywheel.
- **Citation disputes** (new) — user flags a wrong citation on any answer; dispute becomes (a) a review item and (b) an eval-set entry (Part 4 feedback loop).
- **Commitment confirmations** (new) — extracted commitments above threshold auto-accept; below threshold queue for confirmation.

Mechanics: confidence-thresholded auto-accept with sampling audit (N% of auto-accepted items spot-checked); SLA + throughput metrics on the admin dashboard; every decision emits a ledger event (audit trail already exists).

### B. In-turn approvals (synchronous HITL) — LangGraph `interrupt()`
When the agent is about to take a side-effectful action (update CRM, send digest, call an external MCP write tool), the graph interrupts, the SSE stream emits an `approval_required` frame, the chat UI renders an approval card, and the turn resumes via `Command(resume=...)` on approval. The Postgres checkpointer makes this durable — approve tomorrow, the thread resumes from the exact node. This is the primary reason to adopt LangGraph for real (Part 3): interrupts + checkpointing are the features the hand-rolled driver cannot do.

---

## Part 3 — LangGraph deep-agent runtime

Today LangGraph is decorative: `graph.py:build_graph()` registers `_noop` for every node; the hand-rolled
`KennyAgentService._run_graph_inner` does the work. Refresh: make LangGraph the actual runtime, keep the
external contracts (SSE v2 frames, REST API, ledger events) byte-identical so the web app is untouched.

Architecture:
- **StateGraph with real nodes**, reusing existing node functions (plan → llm_call → tool exec → citations → adversarial → finalize) and the already-shared routers.
- **AsyncPostgresSaver checkpointer** (langgraph-checkpoint-postgres) — durable threads, resumability, interrupt support, time-travel debugging of agent runs.
- **Async provider path throughout** — fixes the audit's blocking-I/O bug (sync `httpx.Client` inside `async def` in `adversarial.py:128`, `oracle_chat.py:184` stalls the event loop up to 120s).
- **Streaming**: `astream_events` mapped to the existing SSE v2 frame vocabulary (`delta`, `tool_call`, `citation_verified`, …) plus new `approval_required` frame.
- **Deep-agent patterns** (deepagents-style): planning todo held in graph state; **subagents** — a retrieval subagent (search/walk tools) and a verification subagent (citations + adversarial) with isolated context windows; main thread synthesizes.
- **LangGraph Store** for per-engagement agent memory (learned stakeholder preferences, style).
- **Guardrails preserved as graph constraints**: `recursion_limit`, tool-call cap in state (8/turn), turn timeout wrapper, token-budget pre-charge (all exist today — port, don't rewrite).
- **Cutover gate**: run the 30 golden questions against old and new drivers; new must match or beat on citation-verification rate and leak count (zero) before the hand-rolled driver is deleted.

---

## Part 4 — LongScale testing framework

Prove it works as the corpus grows over years, not just on a fresh seed.

1. **Fix the eval runner** — the flagship CI job has never executed (no test functions collected, unregistered `-m eval` marker, four undefined CLI flags → pytest exit 4 nightly, leak gate skipped). Give `runner.py` a real CLI (`__main__` + argparse), run it directly, PR-gate a deterministic subset.
2. **Derived ground truth** — the XL generator knows the truth it seeds (uuid5-deterministic). Emit (question, expected citation IDs, expected answer facts) pairs from the generator itself. Replaces the deleted synthetic corpus with hundreds of *grounded* cases for free.
3. **Longitudinal replay harness** — seed XL progressively (weeks 26 / 52 / 104 / 156 / 260), run the question set at each checkpoint, record accuracy, citation precision/recall, latency percentiles vs corpus size. Assert degradation bounds (e.g., accuracy drop < 5% from smallest to largest corpus). This is the "does retrieval decay at scale" proof.
4. **Fix the metrics** — hallucination rate currently vacuous (zero citations → 0.0). New: uncited-claim rate via the LLM judge; judge exists as dead code (`runner.py:318`) — wire it, keep substring match as a fast pre-filter.
5. **Leak gate, actually running** — cross-engagement leak count == 0, nightly, hard-fail with alerting. (The RLS fuzzer with its anti-test is the repo's best gate — extend that pattern.)
6. **Load & soak** — k6 API suite; N tenants × M engagements seeded; 24h soak on compose; embedding-queue drain SLO (jobs table exists); MCP server p95 under concurrent tool calls.
7. **Chaos drills** — provider 429/outage (verify failover once real), Postgres restart mid-turn (checkpointer recovery), kill-switch drill (once real).
8. **CI tiers** — PR: deterministic + subset evals; nightly: 5-question LLM eval + leak gate; weekly: full 30 + longitudinal replay; release: load + soak. Also: run the ~105 currently-dark tests (mcp-server incl. tenant isolation, llm-provider-py, `_shared/{authz,runtime,tsa}`).
9. **Eval trends on admin dashboard** — extend the existing dashboard with per-run eval history so degradation is visible, not archaeological.

---

## Part 5 — Legibility: how the product should read (added 2026-08-11, post-Wave-2 UI walkthrough)

Walking the shipped UI with both seeds loaded surfaced a structural problem that no single
ticket above fixes: **screens are organized by database table, not by user job.** The
engagement page opens with raw agent telemetry (`AGENT_TOOL_INVOCATION tool:keyword_search
rows=3 dur=6.2ms`) as its hero content, shows team members as UUIDs, puts an admin form in
the middle of the reading flow, and hides the two differentiators — the evidence graph and
Kenny — below the fold and behind a collapsed rail. The portfolio page leads with three
paragraphs of insight prose before the list of deals. At XL scale (3,888 events) the page
takes seconds to load monolithically and the matrix defaults to an unreadable hairball.
Nothing anywhere answers "what changed since I last looked" or "what needs me."

### The theory: every screen answers three questions, in order

> **What changed? → What needs me? → What do I do next?**

The DRM loop is *Orient → Decide → Act → Ask*. Concretely:

1. **The deal is the unit of attention.** Home is "my deals, ranked by need-attention"
   (open approvals + pending proposals + escalations + overdue commitments + stall
   signals), not a table sorted by updated-at under a wall of insight prose.
2. **The deal page is a briefing, not a dump.** Reading order: header (phase, health,
   next milestone) → *since you last looked* (delta digest, F1) → *needs you* (inline
   action queue: approvals, proposals, escalations — resolvable without leaving) →
   narrative sections (people, decisions, risks, commitments as cards with receipts) →
   exploration tools (graph, timeline) demoted to tabs.
3. **Kenny is the front door, not a side rail.** A persistent "Ask this deal anything"
   composer on the briefing, with suggested questions derived from engagement state.
   Chat opens as a full-width surface. The agent *is* the query language for the graph;
   treat it that way.
4. **Evidence on demand, telemetry never.** Receipts (citations, provenance) expand
   inline where a claim appears. Raw tool invocations, source-kind enums, and duration
   metrics belong on the admin dashboard only.
5. **People are people.** Names, roles, initials — never UUIDs. Member *management*
   lives on a People tab; the briefing shows who matters and when they were last heard
   from.
6. **The graph is a lens, not a landing.** Default to the neighborhood of the selected
   node with type filters and search-to-focus; an 866-node force layout is never shown
   uninvited.
7. **Speed is comprehension.** Summary payload first paint < 1s; sections stream in
   independently with shimmer placeholders; the page is readable before it is complete.

### IA restructure

- Nav: **Home** (attention-ranked portfolio + digest) · **Deals** · **Review** (existing
  inbox) · **Ask** (global Kenny, engagement-scoping chips) · **Admin** (collapsed:
  dashboard, MCP, settings).
- Deal page tabs: **Brief** (default, per above) · **People** · **Graph** · **Timeline**
  · **Chat history**.

Wave 2.5 below turns this into tickets. It intentionally lands *before* Wave 3: F1
(delta digest), F3 (commitments), and F4 (stall alerts) all render INTO the Brief's
"since you last looked" and "needs you" slots — build the slots first, fill them next.

### The demo thesis (added 2026-08-11)

The seeded-corpus demo fails because it shows **state, not motion** — a prospect looking at
a pre-populated matrix can't tell it from a slide. The demo that sells is **the cold start**,
three acts on a fresh engagement:

1. **Capture**: feed 3 recognizable artifacts (kickoff transcript, email thread with a buried
   commitment, Slack export with a passing risk mention) through Capture → watch proposals
   appear → accept/reject with the human gate.
2. **Ask**: put the three killer questions to Kenny — including the refusal trap (a question
   the corpus can't answer, where Kenny declines instead of hallucinating) — and click a
   citation through to the source.
3. **Teach**: escalate the refused question to the team, answer it, re-ask — Kenny now gives
   a cited answer from knowledge entered minutes ago. Coda: flip to BlueState-XL for scale.

Value ranking this implies: cited refusal-capable answers > capture loop with human gate >
escalation flywheel > causality > trust substrate (diligence material, not demo material).
Lists, dashboards, graph viz, and MCP plumbing are table stakes — nobody buys them.
**Wave 3 is re-sequenced to serve this demo**: demo kit (K1–K5) and conviction features
(F3, F1) first; adoption features (F5–F7) after the first pilot converts.

---

## Part 6 — Ticket backlog

Legend: **P0** blocks pilot · **P1** agent/HITL refresh · **P2** DRM features · **P3** scale proof.
Size S/M/L. Lanes are parallel-safe for coding agents (minimal file overlap). Deps listed by ID.

### Wave 0 — hygiene + cheap safety (all parallel, no deps)

| ID | P | Sz | Ticket |
|---|---|---|---|
| B1 | P1 | S | Delete `packages/shared-ui`; archive per docs convention. Salvage nothing (concepts noted in HITL design). |
| B2 | P1 | M | Delete `services/cartographer`; move `triage.py` → `control_plane/services/triage.py` with its tests. |
| B3 | P1 | S | Fold `services/ingest` helpers into `services/_shared`; update 6 importers; delete the service dir. |
| B4 | P1 | S | Delete dead weight: `infra/audit-relay/`, duplicate `src/llm_provider/` pkg, `release-gate.yml`, `tests/continuity-of-reference/`, `tests/golden/queries/` (200 synthetic files), empty `repositories/` pkg. |
| B5 | P2 | S | Docs truth pass: control-plane README ("Story 1.3 scaffold" is stale), `.env.example:88` stale pointer, root README `services/oracle/` refs, MCP `resources.py:221` stale "deferred to Phase 5.5" placeholder + the test asserting it. |
| C1 | P0 | M | CI de-theater: remove/implement `turbo run validate:llm-matrix` (matches no package, exits 0); drop `--passWithNoTests`; set coverage floors (start 60% CP, 50% web); fix or delete `validate:llm-matrix:py` (reads nonexistent `services/config/`). |
| C2 | P0 | S | Wire dark test suites into CI: `services/mcp-server` (26 tests incl. tenant isolation), `packages/llm-provider-py` (27), `services/_shared/{authz,runtime,tsa}` (52). |
| C3 | P0 | S | Gate `cloud-deploy.yml` on CI green (`workflow_run` on ci.yml success, or shared `needs`). Deploy currently races CI. |
| A6 | P0 | S | Slack webhook fail-closed: unset signing secret → reject events (currently processed + committed, `integrations_slack.py:218`). |
| A7 | P0 | M | SSRF guard on MCP outbound endpoints: https-only, hostname allowlist option, deny private/link-local/metadata ranges at config-write AND at request time (DNS rebinding). |
| A9 | P0 | S | MCP `vector_search` fix: kwarg `kinds`→`kind`, inject embedder (currently always -32603, `tools.py:183` vs `search.py:443`). |
| H2 | P0 | S | Fix AGE download URL (`infra/compose/postgres/Dockerfile:17`): archive.apache.org with dlcdn fallback; breaks all cold builds when 1.6.0 rotates. |
| B6 | P1 | S | Reconcile TS/Python citation schema drift (`signed_timestamp`: Zod any-string vs Python RFC 3339 regex); add cross-language contract test so drift fails CI. |

### Wave 1 — trust layer (parallel within wave)

| ID | P | Sz | Deps | Ticket |
|---|---|---|---|---|
| A1 | P0 | L | — | Implement OIDC callback (`api/auth/callback/oidc/route.ts` 501): code exchange, JWKS verify, JIT user, mint session cookie. CP already has OIDC+PKCE machinery — reuse. Drop the Cloudflare Access framing from `docs/ops/cloud-deploy.md:16` or implement the header check; pick one. |
| A2 | P0 | M | — | Web middleware hardening: matcher covers `/admin/*` + `/api/internal/v1/*` (header-strip + edge authz currently bypassed, `middleware.ts:139`); flip `DEPLOYAI_LOCAL_DEV_ROLE_INJECT` to default-off everywhere incl. runbook; `DEPLOYAI_STRATEGIST_REQUIRE_TENANT` default-on. |
| A3a | P0 | M | — | **DONE** (wave-1-trust): migrations `20260811_0051` (tenant_id on ledger edge tables + backfill trigger) and `20260811_0053` (ENABLE+FORCE RLS + `tenant_rls_*` policies on all 40 remaining tenant_id tables → 49/49 covered; exempt: `app_tenants`, `internal_service_tokens`, `webhook_deliveries` — see `tests/integration/test_rls_expansion.py`). Fuzz harness extended 8→20 tables. Follow-up: denormalized tenant_id for `webhook_deliveries`; NOT NULL contract migration for the ledger edge tenant_id. |
| A3b | P0 | L | A3a | **CORE DONE** (wave-1-trust): `get_tenant_db_session`/`TenantDbSession` (db.py) + `TenantScopedRequestSession` (deployai_tenancy) — GUC re-applied per transaction so handlers can commit. Converted: `engagements_internal` (engagements+matrix), `ledger_internal`, `oracle_internal`, `temporal_insights_internal`. Remaining ~33 route modules still on `AppDbSession` — mechanical, parallelizable per module (same swap: `get_app_db_session`→`get_tenant_db_session`, `require_internal`→`require_tenant_scoped` where routes take `tenant_id` query param). |
| A4 | P0 | M | — | **DONE** (wave-1-trust): `config/internal_auth.py` centralizes `require_internal` (12 copies removed) + adds `require_tenant_scoped`; `internal_service_tokens` table (migration `20260811_0052`) + mint/list/revoke routes (`/internal/v1/tenant/service-tokens`, global-key-gated bootstrap). Tenant token naming a foreign `tenant_id` → 403. Legacy global key still accepted with a structured `internal_auth.legacy_global_key_used` warning per use — remove after callers migrate. |
| A5 | P0 | M | — | `packages/authz`: tenant comparison for all resource kinds (today only `kind==="tenant"`, so middleware's own gate never compares tenants); carry `tenantId` on resources; add per-surface actions (matrix:read, agent:ask, admin:read). |
| A8 | P1 | M | — | Kill switch real: OAuth revoke (Google + MS Graph), queue purge, secret delete (all three are `_stub()` today). |
| H1 | P0 | M | — | Fly production backups: scheduled `pg_dump` → S3 (Tigris) + restore drill; scripts today are compose-only. |
| D0 | P0 | M | — | Async LLM provider: async httpx client for chat/stream paths, retries with jitter + `Retry-After` (sync path blocks event loop up to 120s in `adversarial.py:128`, `oracle_chat.py:184`). Prereq for Wave 2. |
| W1 | P1 | S | — | Web resilience: `error.tsx`/`loading.tsx`/`global-error.tsx` per route group + error boundaries. |
| D8 | P1 | M | D0 | Provider truth: either implement real failover (error detection, retry, circuit breaker — today `FailoverProvider` is a static env router) + OpenAI streaming/tools (currently `NotImplementedError`), or delete the failover pretense and go Anthropic-only. Decide, don't carry the lie. |
| D9 | P0 | S | — | Embeddings fail-loud: production mode requires `VOYAGE_API_KEY`; remove silent `pseudo_embed` hash-vector fallback from prod path (dev keeps it behind explicit flag). |
| H3 | P0 | M | — | S3-backed artifact stores: email bodies + transcripts currently local-disk stub / `NotImplementedError` for S3 — wire to MinIO locally, Tigris on Fly. Local-disk on Fly = data loss on redeploy. |

### Wave 2 — LangGraph runtime + HITL core

| ID | P | Sz | Deps | Ticket |
|---|---|---|---|---|
| D1 | P1 | M | — | **DONE** (wave-2-agent): migration `20260811_0054_langgraph_checkpoints` (library DDL captured, setup() pre-seeded no-op), `agents/agent_kenny/checkpointer.py` pooled AsyncPostgresSaver, thread_id = `tenant:{t}:engagement:{e}:conversation:{key}`. Add `langgraph-checkpoint-postgres` AsyncPostgresSaver + Alembic migration for checkpoint tables; thread_id = chat session. |
| D2 | P1 | L | D0,D1 | **DONE** (wave-2-agent): `agents/agent_kenny/runtime.py` wraps the node fns into a checkpointed StateGraph; `KennyAgentService` branches on `DEPLOYAI_AGENT_RUNTIME` (default legacy). Rebuild `graph.py` as real StateGraph: existing node fns as nodes, shared routers, guardrails as graph constraints (recursion_limit, tool cap in state, timeout, budget pre-charge). Feature-flag `DEPLOYAI_AGENT_RUNTIME=langgraph|legacy`. |
| D3 | P1 | M | D2 | **DONE** (wave-2-agent): same emit sink threaded through as custom stream writer (byte-identical frames by construction); kenny-v2 / phase5-stream / golden-smoke integration tests parametrized over both runtimes. Map `astream_events` → SSE v2 frames unchanged; frontend untouched. Golden smoke passes on both runtimes. |
| D4 | P1 | L | D2,D3 | **DONE** (wave-2-agent): `approval_required` frame (additive), `POST .../oracle/approvals/{thread_id}` resume (returns completed reply as JSON, non-streaming — matches the web JSON fallback tier), ledger kinds `agent_approval_requested/granted/denied`, ApprovalCard wired in OracleChat + approvals BFF route; policy in `agents/agent_kenny/approvals.py` (external write verbs + `DEPLOYAI_AGENT_APPROVAL_TOOLS`). `interrupt()` approvals: `approval_required` SSE frame, resume endpoint (`Command(resume=...)`), approval card in chat UI, ledger events for request/decision. |
| D5 | P1 | L | D2 | Deep-agent structure: planning todo in state; retrieval subagent + verification subagent with isolated contexts; adversarial pass becomes confidence-gated (config per tenant) instead of every-turn. |
| D6 | P1 | M | D2,G1 | **GATE SHIPPED** (wave-2-agent): `tests/integration/test_runtime_parity_gate.py` runs an 8-question golden subset (incl. 2 negative + 2 cross-engagement) on both runtimes — verified ≥, unverified ≤, shipped-leak count 0, tool cap held. Legacy driver deliberately NOT deleted this wave. Cutover parity gate: 30 golden questions old-vs-new; new ≥ old on citation-verified rate, leak count 0; then delete hand-rolled driver + legacy `<tool_call>` text parser. |
| D7 | P2 | M | D2 | LangGraph Store: per-engagement agent memory (preferences, glossary); surfaced + editable in settings. |
| E1 | P1 | L | — | Review Inbox: unify extraction proposals + escalations + disputes + commitment confirmations into one queue UI with filters, SLA metrics. Reuses MatrixProposals patterns. |
| E2 | P1 | M | E1 | Escalation flow: low-confidence/failed-verification → decline + escalation item; human answer recorded as canonical ledger event with citations. |
| E3 | P1 | S | E1 | Citation dispute: flag control on answer citations → review item + eval-set entry (feeds G2). |
| E4 | P1 | M | E1 | Confidence-thresholded auto-accept + sampling audit for proposals/commitments; thresholds in tenant settings. |
| F2 | P1 | M | — | Unify `MatrixInsight`/`temporal_insights` models; ship the hidden snooze/follow-up UI (BFF routes exist, `EngagementInsights.client.tsx:232`). |

### Wave 2.5 — Legibility (UX restructure; see Part 5 for the theory)

All of U1–U10 shipped in #273 (merged 2026-08-11).

| ID | P | Sz | Deps | Ticket |
|---|---|---|---|---|
| U1 | P0 | S | — | **DONE** (#273) Quick defects from the walkthrough: insight-card title duplication ("risk closed: Risk closed: …" — the source_kind prefix is prepended to a title that already contains it); TimestampLabel render-loop (fixed in PR #270); raw `source_kind` enums shown as card labels — map to human labels in one shared helper. |
| U2 | P0 | M | — | **DONE** (#273) People are people: resolve member/actor UUIDs to names + roles everywhere (join app_users in the engagement payload; avatar initials from names; "last heard from" from ledger actor timestamps). UUIDs never render in user-facing surfaces. |
| U3 | P1 | L | U1,U2 | **DONE** (#273) Engagement **Brief** layout: reorder the detail page to header+health → "since you last looked" slot (until F1 lands: recent changes grouped by kind with human titles) → "needs you" inline action queue (pending approvals, proposals, escalations with resolve-in-place; reuses Review Inbox APIs) → narrative card sections (people / decisions / risks / commitments) with expandable receipts. Move team management to a People tab; move the agent telemetry strip to the admin dashboard. |
| U4 | P1 | M | U3 | **DONE** (#273) Kenny as front door: persistent ask-bar on the Brief ("Ask this deal anything"), full-width chat surface on submit, suggested questions derived from engagement state (open risks, recent decisions). Rail retired. |
| U5 | P1 | M | — | **DONE** (#273) Graph as a lens: matrix tab defaults to filtered neighborhood view (selected node + N hops, type filters, search-to-focus); virtualize rendering; the full-graph layout is an explicit opt-in. Must stay usable at BlueState-XL scale (866 nodes). |
| U6 | P1 | M | W2 | **DONE** (#273) Progressive loading: engagement summary endpoint for first paint (<1s target), sections fetch independently via react-query with shimmer placeholders; XL page readable-before-complete; kill the monolithic full-payload refetch. |
| U7 | P2 | S | — | **DONE** (#273) Portfolio home reorder: deals table first, ranked by a needs-attention score (open approvals + pending proposals + escalations + stalls); portfolio insights collapse to ranked one-line cards that expand on demand. |
| U8 | P2 | M | U1 | **DONE** (#273) Timeline legibility: narrative day/week clustering with human titles and source icons instead of a flat list of enum-labeled rows; 3,888-event engagements must skim well. |
| U9 | P2 | S | — | **DONE** (#273) Empty/first-run states: every surface says what it is, how data arrives, and the one next action (esp. Review Inbox kinds and the commitments slot). |
| U10 | P2 | M | U4 | **DONE** (#273) Global **Ask** page: Kenny across the portfolio with engagement-scoping chips; per-engagement isolation guarantees unchanged (leak gate already enforces). |

### Wave 3 — demo kit + DRM features (re-sequenced 2026-08-11; see Part 5 "The demo thesis")

Order below is priority order: K1–K5 build the cold-start demo, F3/F1 are the conviction
features that fill the Brief's slots, F5–F7 are adoption features deferred past the first pilot.

| ID | P | Sz | Deps | Ticket |
|---|---|---|---|---|
| K1 | P0 | S | — | `make demo-reset`: idempotent "Acme Robotics — Pilot Deployment" seed — fresh engagement, zero events, plus 3 staged artifact files in `demo/artifacts/` (kickoff transcript, email thread with a buried commitment, Slack export with a passing risk mention). Rerunnable between meetings. |
| K2 | P0 | M | — | Capture tab ingestion UX: drag-drop file upload + paste-a-thread text input → canonical ingest → extraction trigger, with honest "extracting…" progress. Target: <30s artifact-to-proposals turnaround. |
| K3 | P0 | S | — | "Escalate to team" button on ungrounded/IDK chat answers → files the E2 escalation (escalation service + resolve flywheel already built; this is the missing entry point from chat). |
| K4 | P0 | S | K2 | Extraction latency verification + progress states: measure and bound artifact→proposals time on the demo artifacts; surface staged progress instead of a spinner. Demo-reliability work. |
| K5 | P1 | S | K1–K4 | `docs/demo/runbook.md`: the three-act script with exact demo lines, timings, and recovery moves (what to do when extraction is slow, when Kenny refuses unexpectedly, etc.). |
| F3 | P1 | L | E4 | **PROMOTED** — "what did we promise" is the core demo question. Commitment tracking: extraction of promises (owner, due date, source event) as matrix node type; overdue alerts; HITL confirmation below threshold. |
| F1 | P1 | L | F2 | Delta digest: "since last visit" + weekly rollup per engagement (new stakeholders/decisions/risks/commitments, silence flags) from snapshot diffs + temporal_insights. Front page of engagement view. Feeds the DeltaDigest slot built in U3; powers the second-meeting demo ("here's what happened while you were gone"). |
| F4 | P2 | M | F2 | Stall/silence alerts surfaced: trailing-silence + no-next-step detection as dashboard signals + digest entries. |
| F8 | P2 | S | — | Matrix header reframe: "changed since last visit" chips; pass `earliestDate` to slider (prop exists, never passed; window hardcoded 90d). |
| F9 | P2 | S | — | Wire `onExplain` (dead "Explain" button stub for G1.c) to a Kenny prompt about the insight. (Verified still unwired 2026-08-11: `EngagementBrief.client.tsx:441` passes no handler, so the button never renders.) |
| W2 | P2 | M | — | Adopt react-query in web: dedupe, cache, mutation invalidation; kill full-payload refetch-after-every-mutation. |
| W3 | P1 | L | — | Playwright E2E for headline flows: onboarding seed → matrix render → time scrub → proposal accept → Kenny Q&A with citation. Runs vs compose stack in CI. Today E2E = 163 LOC read-only smoke. |
| F5 | P3 | L | — | **DEMOTED** (adoption feature, post-conviction) Kenny in Slack: mention/slash-command → answer with citations (link back to app); reuses existing Slack app + HMAC verify; respects tenant binding of the Slack workspace. |
| F6 | P3 | M | F1 | **DEMOTED** (adoption feature, post-conviction) Outbound weekly digest email (Resend or SES); per-user opt-in; D4 approval optional for first sends. |
| F7 | P3 | L | A4 | **DEMOTED** (adoption feature, post-conviction) HubSpot one-way sync: companies/contacts/deals → stakeholders/engagements; idempotent upsert via external IDs; sync status UI. |

### Wave 4 — LongScale proof

| ID | P | Sz | Deps | Ticket |
|---|---|---|---|---|
| G1 | P0 | M | — | Make eval runner executable: `__main__` + argparse (`--limit --random --report --question-ids`), drop broken pytest invocation, register marker or bypass pytest; PR-gate deterministic subset. Nightly job currently exits 4 and the leak gate has never run. |
| G2 | P3 | L | G1 | Ground-truth derivation: XL/portfolio generators emit (question, expected citations, expected facts) alongside seeds; replaces deleted synthetic corpus with grounded cases. |
| G3 | P3 | L | G2 | Longitudinal replay: progressive seeding (wk 26/52/104/156/260), question set at each checkpoint, accuracy/citation-P-R/latency vs corpus size, degradation bounds asserted. |
| G4 | P1 | M | G1 | Wire LLM judge (`runner.py:318` dead code) behind fast substring pre-filter; fix hallucination denominator (no-citation answers scored, not 0.0). |
| G5 | P0 | S | G1 | Leak gate live: nightly, hard-fail, alert (Slack webhook); `STRICT_EVAL_REQUIRED` actually set. |
| G6 | P3 | L | — | Load/soak: k6 API suite; N-tenant × M-engagement seed; 24h soak; embedding-queue drain SLO; MCP p95 under concurrency. |
| G7 | P3 | M | D2 | Chaos drills: provider 429/outage, Postgres restart mid-turn (checkpointer recovery proof), kill-switch drill. |
| G8 | P3 | M | G1 | Eval trend history on admin dashboard (extend existing dashboard + audit traces). |

### Parallelization notes for coding agents

- Wave 0: all 12 tickets fully parallel (disjoint files).
- Wave 1: A1/A2/W1 (web) vs A3a/A4/A5/A8/D0 (CP) vs H1 (infra) — disjoint. A3b fans out per route module across many agents.
- Wave 2: D-lane (agent runtime) and E-lane (Review Inbox UI+API) are independent until D4 meets E1's UI shell.
- Wave 3: K1–K5 and F1–F9 mostly independent (K4 depends on K2; K5 documents K1–K4); F5/F7 touch integrations only.
- Contract discipline: SSE frame vocabulary and BFF response schemas are the frozen interfaces — any agent touching them must update `packages/contracts` + the drift gate first (TS/Python citation schemas have already drifted on `signed_timestamp`; B6 reconciles this — do it before any contract-touching ticket).

### Sequencing summary

1. Wave 0 + G1/G5 immediately (cheap, kills theater, makes CI honest). — DONE 2026-08-11 (#264)
2. Wave 1 = pilot blocker set. After Wave 1: a startup can log in, data is tenant-safe, prod is backed up, deploys are gated. — DONE 2026-08-11 (#265)
3. Wave 2 = the refresh: real LangGraph runtime + HITL inbox. — DONE 2026-08-11 (#266)
4. **Wave 2.5 = legibility (Part 5)**: the product must *read* before it grows — Brief layout, humanized identity, Kenny as front door, graph-as-lens, progressive loading. U3's digest/needs-you slots are the landing zones Wave 3 fills. — DONE 2026-08-11 (#273)
5. Wave 3 re-scoped (see Part 5 "The demo thesis"): demo kit + conviction features (K1–K5, F3, F1) first; adoption features (F5–F7) after first pilot.
6. Wave 4 = longscale proof for buyer conversations.
