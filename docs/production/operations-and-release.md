# Operations and release (production-facing)

How to think about hosting **DeployAI** (strategist web + control plane) in **dev**, **staging**, and **production** after CI is green. Complements pilot runbooks; does **not** replace [whats-actually-here.md](../../whats-actually-here.md) or [_bmad-output/implementation-artifacts/development-board.yaml](../../_bmad-output/implementation-artifacts/development-board.yaml) for engineering Track **E** truth.

---

## Epic alignment (strategist surfaces)

Ops framing matches [_bmad-output/planning-artifacts/epics.md](../../_bmad-output/planning-artifacts/epics.md): **Epic 8** (digest / phase / evening loaders), **Epic 9** (queues + BFF), **Epic 10** (overrides / audit boundaries). Pilot workflows trend toward **Epic 16**; operators triage via [support-runbook](../pilot/support-runbook.md). **[Lane O](parallel-agent-execution-plan.md)** uses **[ship-fast observability defaults](product-strategy-ship-fast-decisions.md)** (**PS-O-101**–**PS-O-106**).

---

## Environments (summary)

- **Dev:** fixtures + optional compose CP; dev strategist injection possible — not prod parity ([dev-environment.md](../dev-environment.md)).
- **Staging:** production-shaped TLS + vault secrets + `NODE_ENV=production` ([phase-0-checklist](../pilot/phase-0-checklist.md)).
- **Pilot / prod-class:** TLS, JWT or trusted edge headers, CP reachable, queue replica honesty ([whats-actually-here.md](../../whats-actually-here.md)).

---

## Observability (vendor-neutral)

Logs + metrics + correlation IDs minimum bar ([correlation-ids-rollout.md](./correlation-ids-rollout.md)); Gate **1** dashboard spec ([gate-1-dashboard-spec.md](./gate-1-dashboard-spec.md)).

---

## Release & rollback

- Merge bar: **`pnpm turbo run lint typecheck test build`** ([human-ops-runbook.md](../human-ops-runbook.md)).
- Memory queues lose state on deploy ([queue-durability-modes.md](../pilot/queue-durability-modes.md)).
- Re-run hosted Gates **1–2** after rollback ([phase-0-checklist.md](../pilot/phase-0-checklist.md)).

---

## Related

| Doc | Role |
| --- | --- |
| [**deployai-source-of-truth-spec.md**](../product/deployai-source-of-truth-spec.md) | Canonical product + architecture + deployment flags (must match code) |
| [phase-0-checklist.md](../pilot/phase-0-checklist.md) | Hosted gates |
| [gate-1-dashboard-spec.md](./gate-1-dashboard-spec.md) | Gate 1 panels |
| [ci-hosted-gate-1.md](./ci-hosted-gate-1.md) | Optional Actions probes |
| [parallel-agent-execution-plan.md](./parallel-agent-execution-plan.md) | Lane ordering |
| [product-strategy-ship-fast-decisions.md](./product-strategy-ship-fast-decisions.md) | Defaults |
