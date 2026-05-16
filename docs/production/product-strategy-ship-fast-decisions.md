# Product strategy — ship-fast defaults (pilot MVP)

Single-page index of **PS-\*** defaults; expand when counsel mandates deltas.

## Ops / observability defaults

| ID | Default |
| --- | --- |
| PS-O-101 | Gate 1 via manual/synthetic/docs + optional GH Actions probe — no vendor SDK lock-in. |
| PS-O-102 | Structured logs + secret scrub + **`correlation_id`**. |
| PS-O-103 | Pilot-light routing (shared Slack/channel) vs paging unless policy mandates 24×7. |
| PS-O-104 | Pilot backup owner = engineering lead until formal ops + runbook skeleton. |
| PS-O-105 | Normalize correlation headers → `correlation_id` field for search. |
| PS-O-106 | GitHub Actions secret mirrors mapped once privately ([ci-hosted-gate-1.md](./ci-hosted-gate-1.md)). |
| PS-L-001 | Dashboards/communications avoid “SLA” unless counsel signs wording. |

## Global rule

Use **`BLOCKED — need human`** only for real secrets, contractual SLAs, legal classification gaps, or unavailable customer IDs — not vendor preference.

## Still human-operated

Vault paths, PEM/private secrets, cloud restore clicks, org GH secret naming policies.

See also [parallel-agent-execution-plan.md](./parallel-agent-execution-plan.md), [agent-followup-prompts.md](./agent-followup-prompts.md).
