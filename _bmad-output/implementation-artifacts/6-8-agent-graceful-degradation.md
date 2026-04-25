# Story 6-8 — Agent graceful degradation (done)

**Strategist:** `AgentErrorState`, `agent_error_to_canonical_payload`, Prometheus `agent_failures_total` + `record_agent_failure`.

**Cartographer:** `degradation_graph.py` — LangGraph with explicit `agent_error` terminal and retry hint in payload. Unit tests: happy path vs `fail: True`.

**Follow-up:** wire OTel spans in agent workers; Epic 8 surfaces consume `agent_error` events.
