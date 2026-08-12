# Engineering Highlights

A guided index for engineers evaluating this codebase. Every claim links to the code
that implements it and the test or CI gate that proves it. Nothing here is aspirational —
if a mechanism is partial, the caveat is stated inline.

The product in one line: an evidence-linked deal-memory graph with a citation-verified
LLM agent and human-in-the-loop review, built for deployment/forward-deployed teams.

---

## 1. The agent is accountable — citations verified against the database

Every `[event:UUID]` / `[node:UUID]` citation in an agent reply is checked with
tenant- and engagement-scoped SELECTs before the user sees it; unverifiable claims are
revised or flagged, and a citation pointing into *another engagement* hard-rejects the
entire reply and writes a security audit event.

- Verification: [`services/control-plane/src/control_plane/agents/agent_kenny/nodes/citations.py`](../services/control-plane/src/control_plane/agents/agent_kenny/nodes/citations.py)
- Leak gate (reply replaced, ledger event emitted): exercised by
  [`tests/integration/test_phase3_cross_engagement_leak.py`](../services/control-plane/tests/integration/test_phase3_cross_engagement_leak.py)
- Refusal behavior is a *feature*: ask about something not in the corpus and the agent
  declines with nearest real matches instead of confabulating (observable in any live
  session; negative-control questions in the golden set pin it).

## 2. Zero-tolerance leak gate in CI

The eval harness runs golden questions (including cross-engagement probes) against a
self-provisioned Postgres testcontainer with the real seed; a single cross-engagement
leak fails the build unconditionally, and a deterministic subset blocks every PR.

- Runner + CLI: [`services/control-plane/tests/golden/agent_kenny/runner.py`](../services/control-plane/tests/golden/agent_kenny/runner.py)
- Workflows: [`.github/workflows/agent-kenny-eval.yml`](../.github/workflows/agent-kenny-eval.yml)
  (nightly/weekly) and the blocking `agent-kenny-pr-gate` job in
  [`ci.yml`](../.github/workflows/ci.yml)
- Honest metrics: an uncited factual answer counts as fully unverified — silence cannot
  game the hallucination rate.

## 3. Tenant isolation with an adversarial proof

Row-level security (FORCE) on every tenant-scoped table, per-tenant service tokens, and
a cross-tenant fuzz harness that runs ~10,000 attack attempts per CI run — including an
**anti-test** that disables RLS and asserts the fuzzer catches the resulting leak, so the
gate is proven able to fail.

- RLS expansion + catalog test (new tenant tables cannot ship without a policy):
  [`services/control-plane/alembic/versions/20260811_0053_rls_expansion.py`](../services/control-plane/alembic/versions/20260811_0053_rls_expansion.py),
  [`tests/integration/test_rls_expansion.py`](../services/control-plane/tests/integration/test_rls_expansion.py)
- Fuzz harness + anti-test: [`.github/workflows/fuzz.yml`](../.github/workflows/fuzz.yml),
  [`services/control-plane/src/control_plane/fuzz/`](../services/control-plane/src/control_plane/fuzz/)

## 4. Durable agent runtime with human-gated side effects

The agent runs on a checkpointed LangGraph StateGraph (Postgres saver, tenant-scoped
thread keys). Side-effectful tools pause the graph via `interrupt()`, stream an
`approval_required` frame to an approval card in chat, and resume from the exact node —
even from a different process.

- Runtime: [`services/control-plane/src/control_plane/agents/agent_kenny/runtime.py`](../services/control-plane/src/control_plane/agents/agent_kenny/runtime.py),
  checkpointer in [`checkpointer.py`](../services/control-plane/src/control_plane/agents/agent_kenny/checkpointer.py)
- Approvals: [`approvals.py`](../services/control-plane/src/control_plane/agents/agent_kenny/approvals.py) +
  [`tests/integration/test_agent_kenny_approvals.py`](../services/control-plane/tests/integration/test_agent_kenny_approvals.py)
- The runtime swap was **parity-gated**: key integration suites run against both the
  legacy hand-rolled driver and the LangGraph driver, and a golden-question parity test
  gates cutover — [`tests/integration/test_runtime_parity_gate.py`](../services/control-plane/tests/integration/test_runtime_parity_gate.py)

## 5. Human-in-the-loop as a knowledge flywheel

Extractions, agent escalations, and citation disputes flow through one Review Inbox.
Resolving an escalation with an answer records it as a *canonical, cited ledger event* —
the next person's question grounds on knowledge entered seconds earlier.

- [`services/control-plane/src/control_plane/services/review_inbox.py`](../services/control-plane/src/control_plane/services/review_inbox.py)
  (`human_escalation_answer` write path), UI under
  [`apps/web/src/app/(strategist)/review/`](../apps/web/src/app/(strategist)/review/)
- Confidence-thresholded auto-accept uses a deterministic hash-based sampling audit —
  reproducible, not `random()`:
  [`services/proposal_auto_accept.py`](../services/control-plane/src/control_plane/services/proposal_auto_accept.py)

## 6. Everything is evidence

The ledger is append-only **by database trigger**, not convention; matrix nodes carry
`evidence_event_ids` back to source events; causal edges (`caused_by`/`affects`) power
provenance chains the UI renders as expandable trees.

- Append-only trigger: [`alembic/versions/20260422_0001_canonical_memory_schema.py`](../services/control-plane/alembic/versions/20260422_0001_canonical_memory_schema.py)
- Graph mirror in Apache AGE for Cypher traversal, with escaping hardened against
  quote/dollar injection in titles:
  [`domain/canonical_memory/age_sync.py`](../services/control-plane/src/control_plane/domain/canonical_memory/age_sync.py)

## 7. Guardrails against the LLM itself

Per-turn tool-call caps, hard timeouts, per-tenant daily token budgets charged *before*
the turn, prompt-injection envelopes around external MCP results, and four ordered
guards on outbound MCP calls — kill switch → allow-list → rate limit → SSRF egress guard
(private/metadata IP ranges blocked with DNS-rebinding re-resolution per connect).

- Egress guard: [`services/egress_guard.py`](../services/control-plane/src/control_plane/services/egress_guard.py)
- Ordered guards + distinct audit kinds per denial reason:
  [`agents/agent_kenny/mcp_client.py`](../services/control-plane/src/control_plane/agents/agent_kenny/mcp_client.py)

## 8. Scale is tested, not asserted

A deterministic 5-year scenario generator (~3,900 ledger events, 70 stakeholders,
uuid5-idempotent) doubles as the eval corpus. The longitudinal harness reseeds it at
five horizons and asserts retrieval quality stays within bounds as the corpus grows —
with the leak gate enforced at every horizon. (Wave 4S — see
[`docs/agent-kenny/eval.md`](./agent-kenny/eval.md) for the current CLI.)

- Generator: [`services/control-plane/src/control_plane/scenarios/bluestate_xl/`](../services/control-plane/src/control_plane/scenarios/bluestate_xl/)

## 9. The numbers

~1,900 tests: ~700 control-plane unit, ~570 integration against real Postgres
(pgvector + migrations to head, per-test truncation isolation), ~500 web (vitest + RTL),
plus authz/tenancy/provider/MCP suites. mypy strict and TypeScript strict clean.
WCAG-AA contrast asserted by the design-token test suite; axe/pa11y in CI. All GitHub
Actions SHA-pinned; SBOM + CVE scan with Critical-blocks.

---

*Where things are honest about limits: OIDC login is built but needs an issuer
registered before customer pilots (bootstrap token access in the interim); the legacy
agent driver remains the production default until the parity gate has soaked; ~33 CP
route modules still use the app-level session pending mechanical RLS adoption. See
[`docs/plans/2026-08-11-pilot-refresh-backlog.md`](./plans/2026-08-11-pilot-refresh-backlog.md)
for the full ledger of what's done and what's next.*
