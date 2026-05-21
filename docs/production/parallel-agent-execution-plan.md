# Parallel agent execution plan (production roadmap)

**Purpose:** Order parallel work across lanes **I/D/Q/M/W/O** without breaking merge safety.

**Defaults:** [product-strategy-ship-fast-decisions.md](./product-strategy-ship-fast-decisions.md) + [source-of-truth spec](../product/deployai-source-of-truth-spec.md) §13.

## Phases (serial)

0 Foundations → 1 Auth/tenant → 2 CP-backed queues → 3 Data plane depth → 4 Ops hardening.

## Lane O (Ops)

| ID | Task | Notes |
| --- | --- | --- |
| O-101 | Gate 1 dashboard/spec | Vendor-neutral; PS-O-101 |
| O-102 | Correlation logging | PS-O-102 / PS-O-105 |
| O-103 | Replica guardrail alarms | Pilot-light routing PS-O-103 |
| O-104 | Backup/restore skeleton | PS-O-104 |

Serialize CP migration ownership (**Q-101**).

## Checkpoints

`pnpm turbo run lint typecheck test build` every PR; hosted [phase-0-checklist.md](../pilot/phase-0-checklist.md) before visitors.

## Links

- [**Canonical product spec (code truth)**](../product/deployai-source-of-truth-spec.md)
- [operations-and-release.md](./operations-and-release.md), [identity-and-tenancy.md](./identity-and-tenancy.md), [strategist-data-plane.md](./strategist-data-plane.md), [strategist-queues-and-replicas.md](./strategist-queues-and-replicas.md)
