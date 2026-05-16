# Gate 1 observability dashboard (spec)

Aligned with **[phase-0 Gate 1](../../pilot/phase-0-checklist.md)**.

**Ship-fast ([PS-O-101](product-strategy-ship-fast-decisions.md)):** Manual + synthetic checks or [.github/workflows/gate-1-hosted-verification.yml](../../.github/workflows/gate-1-hosted-verification.yml) ([ci-hosted-gate-1.md](./ci-hosted-gate-1.md)).

## Panels

1. CP `GET /healthz`
2. Postgres dependency health
3. Web TLS / synthetic HTTPS
4. Web RED baseline
5. Optional pilot-readiness placeholder (not SLA)

## Logs

**PS-O-102:** structured JSON + **`correlation_id`**; scrub secrets ([correlation-ids-rollout.md](./correlation-ids-rollout.md)).
