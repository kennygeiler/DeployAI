# Inbound API rate limiting (control plane)

Per-principal token-bucket limiting on the control plane's public surface.
Implemented as FastAPI middleware in
`services/control-plane/src/control_plane/infra/rate_limit.py`.

**Disabled by default.** Nothing changes for existing deployments until an
operator sets the env below.

## Environment

| Env | Default | Meaning |
| --- | --- | --- |
| `DEPLOYAI_API_RATE_LIMIT_PER_MINUTE` | `0` (disabled) | Sustained per-principal request budget. `0`/unset = middleware is a pass-through. |
| `DEPLOYAI_API_RATE_LIMIT_BURST` | = per-minute value | Bucket capacity (max burst above the sustained rate). |
| `DEPLOYAI_REDIS_URL` | unset | When set in the process env, the limiter uses Redis (fleet-wide). Unset = in-memory, single instance. |

## Scope

Applies to every public route (auth, integrations, platform, SCIM, uploads).
Exempt — these must never 429:

- `/internal/*` — already gated by `X-DeployAI-Internal-Key` / service tokens
- `/healthz`, `/health`, `/readyz` — probes
- `/metrics` — Prometheus scrape

## Keying (who gets a bucket)

Auth resolution (JWT verification, service-token lookup) runs in route
dependencies — *after* middleware — so the limiter cannot see
`tenant_id + subject` without verifying every token twice per request.
Instead, in order:

1. `Authorization` header present → `auth:<sha256(header)[:32]>` — stable per
   principal for the token's lifetime; the raw credential is never stored.
2. Session access cookie (`dep_access`) → `cookie:<sha256(value)[:32]>`.
3. Otherwise client IP: first `x-forwarded-for` hop, falling back to the
   socket peer. Trusting the first hop assumes the ingress strips/appends
   XFF correctly — that is the load balancer's job.

## Backends

- **Redis** (`DEPLOYAI_REDIS_URL` set): atomic `INCR` + `PEXPIRE`
  fixed-window counter — `burst` requests per 60s window, shared across all
  control-plane instances. Fixed-window rather than Lua token bucket because
  the test backend (fakeredis without lupa) cannot run scripts; `INCR` is
  atomic so concurrent instances never double-admit. Redis errors **fail
  open** (availability over enforcement) with a warning log.
  Note: `settings.redis_url` has a dev default, so the *process env var* is
  the opt-in signal — the settings field alone does not enable Redis limiting.
- **In-memory** (env unset): continuous-refill token bucket in a
  process-local dict. Known limitation, on purpose: protects a single
  instance only and resets on every deploy/restart (same trade-off as the
  web demo limiter, `apps/web/src/lib/internal/demo-rate-limit.ts`). Set
  `DEPLOYAI_REDIS_URL` for anything multi-instance.

## Rejection shape

- Status `429`, body `{"error": "rate_limited"}`
- `Retry-After: <seconds>` (ceil, minimum 1)
- Prometheus: `deployai_rate_limited_total{route=<route template>}` — labelled
  by route template (bounded cardinality), not raw path.
