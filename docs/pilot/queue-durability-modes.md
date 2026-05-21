# Strategist queue durability (pilot)

**Current behavior:** strategist **action / validation / solidification** queues are **only** persisted in **Postgres** via the control plane (`/internal/v1/strategist/*-queue-items`). The Next.js BFF **proxies** to those endpoints; there is **no** in-process queue store in `apps/web`.

## Requirements

- **`DEPLOYAI_CONTROL_PLANE_URL`** and **`DEPLOYAI_INTERNAL_API_KEY`** set on the web tier.
- Control-plane DB migrated (including strategist queue tables).
- If env is missing or CP is unreachable, BFF queue routes return **503** / **degraded** JSON (no silent fallback).

## Record your choice

Record tenant + CP endpoints for each hosted environment in your environment runbook; see the [source-of-truth spec](../product/deployai-source-of-truth-spec.md) §7 and §13 for the queue-durability contract.
