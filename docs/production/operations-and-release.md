# Operations and release (production-facing)

How to think about hosting **DeployAI** (strategist web + control plane) in **dev**, **staging**, and **production** after CI is green. Complements pilot runbooks; the root [`README.md`](../../README.md) and [`docs/agent-kenny/INDEX.md`](../agent-kenny/INDEX.md) are the current product reference (pre-v2 [source-of-truth spec](../archive/product/deployai-source-of-truth-spec.md) and [delivery-status.yaml](../archive/delivery-status.yaml) preserved in archive).

---

## Epic alignment (strategist surfaces)

Ops framing matches the epic structure (archived [epics.md](../archive/epics.md)): **Epic 8** (digest / phase / evening loaders), **Epic 9** (queues + BFF), **Epic 10** (overrides / audit boundaries). Pilot workflows trend toward **Epic 16**; operators triage via [support-runbook](../pilot/support-runbook.md). **[Lane O](parallel-agent-execution-plan.md)** uses **[ship-fast observability defaults](product-strategy-ship-fast-decisions.md)** (**PS-O-101**–**PS-O-106**).

---

## Environments (summary)

- **Dev:** fixtures + optional compose CP; dev strategist injection possible — not prod parity ([dev-environment.md](../dev-environment.md)).
- **Staging:** production-shaped TLS + vault secrets + `NODE_ENV=production` ([phase-0-checklist](../pilot/phase-0-checklist.md)).
- **Pilot / prod-class:** TLS, JWT or trusted edge headers, CP reachable, queue replica honesty (historical §9, §13 of archived [source-of-truth spec](../archive/product/deployai-source-of-truth-spec.md)).

---

## Observability (vendor-neutral)

Logs + metrics + correlation IDs minimum bar ([correlation-ids-rollout.md](./correlation-ids-rollout.md)); Gate **1** dashboard spec ([gate-1-dashboard-spec.md](./gate-1-dashboard-spec.md)).

---

## Release & rollback

- Merge bar: **`pnpm turbo run lint typecheck test build`** (operator setup in [`docs/dev-environment.md`](../dev-environment.md); pre-v2 runbook archived at [`docs/archive/human-ops-runbook.md`](../archive/human-ops-runbook.md)).
- Memory queues lose state on deploy ([queue-durability-modes.md](../pilot/queue-durability-modes.md)).
- Re-run hosted Gates **1–2** after rollback ([phase-0-checklist.md](../pilot/phase-0-checklist.md)).

---

## Related

| Doc | Role |
| --- | --- |
| Root [`README.md`](../../README.md) + [`docs/agent-kenny/INDEX.md`](../agent-kenny/INDEX.md) | Current canonical product + architecture (post-v2 ship). Pre-v2 [source-of-truth spec](../archive/product/deployai-source-of-truth-spec.md) archived. |
| [phase-0-checklist.md](../pilot/phase-0-checklist.md) | Hosted gates |
| [gate-1-dashboard-spec.md](./gate-1-dashboard-spec.md) | Gate 1 panels |
| [ci-hosted-gate-1.md](./ci-hosted-gate-1.md) | Optional Actions probes |
| [parallel-agent-execution-plan.md](./parallel-agent-execution-plan.md) | Lane ordering |
| [product-strategy-ship-fast-decisions.md](./product-strategy-ship-fast-decisions.md) | Defaults |
