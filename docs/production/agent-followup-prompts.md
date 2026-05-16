# Agent follow-up prompts (production lanes)

Workers **must read [`product-strategy-ship-fast-decisions.md`](./product-strategy-ship-fast-decisions.md)** first unless @human overrides.

Use **`BLOCKED — need human`** only for secrets, binding legal/commercial constraints, or missing customer identifiers — not observability vendor picks.

## 1 — Identity (I)
Implement Lane I (`parallel-agent-execution-plan.md`, `identity-and-tenancy.md`); PS-I-* defaults.

## 2 — Data plane (D)
Lane D + `strategist-data-plane.md`; PS-D-*.

## 3 — Queues (Q)
Lane Q + `strategist-queues-and-replicas.md`; serialize **Q-101** migrations.

## 4 — Meetings (M)
Lane M + `docs/pilot/meeting-presence-pilot-scope.md`; PS-M-*.

## 5 — Web / BFF (W)
Lane W; PS-W-* + Epic 10 audit honesty.

## 6 — Ops (O)
Lane O + `operations-and-release.md`, `gate-1-dashboard-spec.md`, `correlation-ids-rollout.md`, `ci-hosted-gate-1.md`, `deploy-queue-replica-guardrail.md`; PS-O-* / PS-L-* — no proprietary vendor SDK assumptions.
