# `deployai-master-strategist`

Epic 6 **Stories 6-6–6-8** — internal-only (no user Strategist UI in V1, DP10).

- **6-6 / FR26:** `src/master_strategist/arbitrate.py` — `arbitrate_proposals()` scores Cartographer + Oracle proposals, routes to Action Queue, User Validation Queue, or suppression + audit.
- **6-7 / FR31:** `src/master_strategist/phase_propose.py` — `build_phase_transition_bundle()` + `build_control_plane_propose_body()` aligned with control plane `POST .../phase-transitions/propose`.
- **6-8 / FR46, NFR11, NFR73:** `degradation.py` (`AgentErrorState`), `metrics.py` (`agent_failures_total`), and **Cartographer** `degradation_graph.py` for a LangGraph `agent_error` terminal.

```bash
cd services/master_strategist
uv sync
uv run pytest
```

Turborepo: `@deployai/master-strategist`.
