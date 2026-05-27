# Product documentation

| Document | Audience | Purpose |
| --- | --- | --- |
| Root [**`README.md`**](../../README.md) | Everyone (customer, new engineer, evaluator) | The customer-facing landing — what DeployAI does, quickstart, feature inventory, architecture, where to find more. Start here. |
| [**`docs/agent-kenny/INDEX.md`**](../agent-kenny/INDEX.md) | Engineers, advisors | Hub for every Agent Kenny doc — ethos, scope, eval, plus pointers to the code that ships each phase. |
| [**Agent Kenny — Ethos**](../agent-kenny/ethos.md) | Engineers, advisors | Architectural decision behind the v2 agent layer + the inspirations (Karpathy LLM Wiki, MCP, LangGraph) we drew from. Reference for "why this shape?" questions. |
| [**Agent Kenny — Scope v2**](../agent-kenny/scope-v2.md) | Engineers | Phase-by-phase build record for Agent Kenny v2 — all phases shipped, with merged-PR pointers. Historical. |
| [**Cartographer (matrix extraction agent)**](./matrix-extraction-agent.md) | Engineers | Design record for the LLM agent that turns canonical events into typed matrix proposals. |
| [**Deployment matrix model**](./deployment-matrix-model.md) | Engineers | The typed property-graph schema (stakeholders, systems, decisions, risks, commitments, opportunities) that Kenny reads against. |
| [**Synthesis agents (Oracle / Master Strategist)**](./synthesis-agents.md) | Engineers | The Phase 7.1 single-shot synthesis agents — kept as compatibility shims; new code uses Agent Kenny. |

**Archived pre-v2 planning docs** (PRD, architecture, epics, product briefs, prior consolidated source-of-truth spec, BMAD delivery tracker, retired edge-agent + FOIA-CLI docs): [`docs/archive/`](../archive/).
