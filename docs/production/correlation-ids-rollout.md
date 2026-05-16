# Correlation identifiers — pilot rollout

Propagate **`X-DeployAI-Correlation-Id`** web→CP; log **`correlation_id`**. Opaque UUID only (**PS-M-103**, **PS-O-102**).

- Middleware ensures **`x-deployai-correlation-id`** on matched strategist/admin routes (`apps/web/middleware.ts`).
- `loadStrategistActivityForActor` forwards the same opaque id (or generates one) as **`X-DeployAI-Correlation-Id`** on CP internal fetches.

**Implementation note:** this checkout does **not** yet include a distinct FastAPI middleware or **`deployai.internal_access`** logger under `services/control-plane` verified by repo search — treat CP-side correlation **logging/traces** as a **follow-through** vs this document, or add the middleware and reconcile with **`docs/product/deployai-source-of-truth-spec.md`**.
