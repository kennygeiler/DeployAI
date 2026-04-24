# Story 4.1: LangGraph Postgres checkpointing against stub agent (AR6)

**Status:** done (implementation landed 2026-04-24; paths under `services/cartographer` + `services/_shared/checkpointer`)  
**Epic:** [epics.md §Epic 4](../planning-artifacts/epics.md) · **Sprint:** `sprint-status.yaml`

## User story

As a **platform engineer**, I want LangGraph checkpointing wired to Postgres against a stub agent that emits canned citation envelopes, so that replay-parity can validate agent behavior before real agents exist.

## References

- **AR6** (architecture): LangGraph + Postgres checkpointing, replay-parity (NFR51)
- **Epic 1:** Citation envelope v0.1, LLM abstraction interface
- **Party Mode (Winston):** Harness before agent — replay acceptance must be buildable first

## Acceptance criteria (from epics)

1. **`services/cartographer/stub_graph.py`** — simple 3-node LangGraph state machine (stub).
2. **Checkpoints in Postgres** — `services/cartographer/migrations/checkpoints.sql` documents runtime DDL from `AsyncPostgresSaver.setup()`.
3. **`services/_shared/checkpointer` (`deployai_checkpointer`)** — `async_postgres_saver` + `checkpointer_thread_id` for tenant-scoped thread ids; prod RLS to layer on same DB role patterns as control-plane.
4. **Canned citation envelopes** — every state transition produces output matching `packages/contracts` / Epic 1 envelope v0.1.
5. **Replay test** — re-run from checkpoint; assert **bit-identical** (or structurally identical per contract) output vs first run.
6. **Tests:** `tests/test_stub_graph_memory.py` (InMemory replay identity) + `tests/integration/test_stub_graph_postgres.py` (Postgres + `alist` has checkpoints).

## Out of scope (later stories)

- Real Cartographer/Oracle agents (Epic 6+)
- Production LLM calls (use stub / canned envelope only)
- Full golden corpus (4.3+)

## Dev notes

- Verify LangGraph version against `uv` / monorepo constraints; add deps in the workspace that will host the graph (likely `services/control-plane` or new `services/cartographer` package).
- Keep checkpoint tables **tenant-scoped** (column + RLS or namespacing) so cross-tenant leaks remain impossible.
- Run `uv run pytest` + integration tests in CI pattern established for control-plane.

## Completion

- [x] Code + tests (unit + optional Docker integration)
- [x] `sprint-status.yaml` story `4-1-langgraph-postgres-checkpointing-stub-agent` → `done`
- [ ] `epic-4` remains `in-progress` for stories 4-2+ (or close when epic completes)
