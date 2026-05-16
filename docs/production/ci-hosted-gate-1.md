# CI — hosted Gate 1 verification (optional)

| Workflow | Trigger |
| --- | --- |
| [.github/workflows/gate-1-hosted-verification.yml](../../.github/workflows/gate-1-hosted-verification.yml) | `workflow_dispatch` |

Set variable `GATE1_HOSTED_CHECKS_ENABLED=true` and secrets `GATE1_CP_HEALTH_URL`, optional `GATE1_WEB_PROBE_URL` ([vault-secret-names.template.md](./config-templates/vault-secret-names.template.md)).

**Human-operated ([PS-O-106](product-strategy-ship-fast-decisions.md)):** Map vault logical names → GitHub mirrors privately.

Does **not** replace Gates **2, 4–6**.
