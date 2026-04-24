# Story 4.1: LangGraph Postgres checkpointing against stub agent (AR6)

**Status:** in-progress (Epic 4 started 2026-04-24)  
**Epic:** [epics.md §Epic 4](../planning-artifacts/epics.md) · **Sprint:** `sprint-status.yaml`

## User story

As a **platform engineer**, I want LangGraph checkpointing wired to Postgres against a stub agent that emits canned citation envelopes, so that replay-parity can validate agent behavior before real agents exist.

## References

- **AR6** (architecture): LangGraph + Postgres checkpointing, replay-parity (NFR51)
- **Epic 1:** Citation envelope v0.1, LLM abstraction interface
- **Party Mode (Winston):** Harness before agent — replay acceptance must be buildable first

## Acceptance criteria (from epics)

1. **`services/cartographer/stub_graph.py`** — simple 3-node LangGraph state machine (stub).
2. **Checkpoints in Postgres** — migration / DDL under `services/cartographer/migrations/checkpoints.sql` (or align with existing `services/control-plane/alembic` if cartographer is not a separate service yet: **use repo layout in architecture**; if no `services/cartographer/`, create minimal package or place under `services/control-plane` with Alembic revision — resolve in implementation PR).
3. **`services/_shared/checkpointer.py`** (or `packages/…`) — wrap LangGraph `PostgresSaver` (or current LangGraph checkpointer API) with **tenant-scoped** session / connection injection consistent with `TenantScopedSession` / RLS.
4. **Canned citation envelopes** — every state transition produces output matching `packages/contracts` / Epic 1 envelope v0.1.
5. **Replay test** — re-run from checkpoint; assert **bit-identical** (or structurally identical per contract) output vs first run.
6. **Integration test matrix:** fresh run → checkpoint present → reload from checkpoint → replay.

## Out of scope (later stories)

- Real Cartographer/Oracle agents (Epic 6+)
- Production LLM calls (use stub / canned envelope only)
- Full golden corpus (4.3+)

## Dev notes

- Verify LangGraph version against `uv` / monorepo constraints; add deps in the workspace that will host the graph (likely `services/control-plane` or new `services/cartographer` package).
- Keep checkpoint tables **tenant-scoped** (column + RLS or namespacing) so cross-tenant leaks remain impossible.
- Run `uv run pytest` + integration tests in CI pattern established for control-plane.

## Completion

- [ ] Code + tests merged to `main`
- [ ] `sprint-status.yaml` story `4-1-langgraph-postgres-checkpointing-stub-agent` → `done`
- [ ] `epic-4` remains `in-progress` until 4-8 (or per team).
