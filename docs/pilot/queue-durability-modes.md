# Strategist queue durability (pilot)

**Current behavior:** strategist **action / validation / solidification** queues are **only** persisted in **Postgres** via the control plane (`/internal/v1/strategist/*-queue-items`). The Next.js BFF **proxies** to those endpoints; there is **no** in-process queue store in `apps/web`.

## Requirements

- **`DEPLOYAI_CONTROL_PLANE_URL`** and **`DEPLOYAI_INTERNAL_API_KEY`** set on the web tier.
- Control-plane DB migrated (including strategist queue tables).
- If env is missing or CP is unreachable, BFF queue routes return **503** / **degraded** JSON (no silent fallback).

## Record your choice

Document tenant + CP endpoints in [`whats-actually-here.md`](../../whats-actually-here.md) §2/§10 for each hosted environment.
