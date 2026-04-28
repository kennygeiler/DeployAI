# Strategist queue durability (pilot)

**Epic 9 today:** action / validation / solidification queues in `apps/web` use **`strategist-queues-store`** — **in-process** memory (see file header in [`strategist-queues-store.ts`](../../apps/web/src/lib/bff/strategist-queues-store.ts)).

## Option A — CP/DB-backed queues (multi-replica safe)

- Implement internal CP APIs (or extend existing routes) with the same shapes the BFF exposes today.
- Point `apps/web` BFF handlers at CP instead of the in-process store.
- **Use when:** more than one `next` instance, or queue state must survive deploys.

## Option B — Single-replica contract (pilot default until A lands)

- Run **one** web replica for the pilot.
- Accept that **queue rows reset** on process restart or redeploy.
- Document in the design partner brief; add monitoring that **replica count = 1** if on Kubernetes.

## Record your choice

Update [`whats-actually-here.md`](../../whats-actually-here.md) §2/§10 when moving from B → A.
