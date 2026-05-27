# Correlation identifiers — pilot rollout

Propagate **`X-DeployAI-Correlation-Id`** web→CP; log **`correlation_id`**. Opaque UUID only (**PS-M-103**, **PS-O-102**).

- Middleware ensures **`x-deployai-correlation-id`** on matched strategist/admin routes (`apps/web/middleware.ts`).
- `loadStrategistActivityForActor` forwards the same opaque id (or generates one) as **`X-DeployAI-Correlation-Id`** on CP internal fetches.

**Implementation note:** if CP-side correlation logging / traces lag this contract, treat it as a follow-through. (Pre-v2 reference: archived [`docs/archive/product/deployai-source-of-truth-spec.md`](../archive/product/deployai-source-of-truth-spec.md).)
