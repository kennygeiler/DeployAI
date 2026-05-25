# Engagement detail aggregate — query budget

Audit date: 2026-05-24 (Phase D D1.d).

## What this covers

The `GET /api/bff/engagements/[engagementId]` BFF route hydrates the
engagement-detail page in one round-trip. It fans out to five (then
six, counting the upstream `cpGetEngagement`) internal control-plane
endpoints — see `apps/web/src/app/api/bff/engagements/[engagementId]/route.ts`.

## CP HTTP calls per request

1. `GET /internal/v1/engagements/{id}` — fetch the engagement row
2. `GET /internal/v1/engagements/{id}/members` — fetch team
3. `GET /internal/v1/engagements/{id}/matrix/nodes` — matrix nodes
4. `GET /internal/v1/engagements/{id}/matrix/edges` — matrix edges
5. `GET /internal/v1/engagements/{id}/proposals?status=pending` — open proposals
6. `GET /internal/v1/tenants/{tid}/node-types` — custom node types

Calls 2–6 fan out in `Promise.all` after #1 resolves. Net wall-clock is
roughly `latency(1) + max(latency(2..6))`.

## DB queries per request (CP side)

Per `services/control-plane/src/control_plane/api/routes/engagements_internal.py`:

- `get_engagement` — 1 query (engagement lookup)
- `list_engagement_members` — 2 queries (`_require_engagement` guard +
  members select)
- `list_matrix_nodes` — 2 queries (`_require_engagement` + nodes select)
- `list_matrix_edges` — 2 queries (`_require_engagement` + edges select)
- `list_matrix_proposals` — 2 queries (`_require_engagement` + proposals select)
- node-types route — bounded; see `resolve_allowed_node_types` (1–2
  queries depending on whether a tenant has overrides)

Total per engagement-detail page load: **~10–11 SQL statements** spread
across six CP HTTP requests. None of these is a true n+1 in the
loop-over-rows sense: every collection-fetch is a single
`SELECT ... WHERE engagement_id = ?`, no per-row follow-ups.

## Repeated-engagement-fetch redundancy

`_require_engagement` is called inside endpoints 2–5 (4 redundant
fetches of the same row). This isn't n+1 — it's a per-endpoint guard,
and each endpoint owns its own transaction, so the row could in
principle change between calls. The simplification path is a true
CP-side aggregate endpoint (`GET /engagements/{id}/detail`) — out of
scope for D1.d because it requires CP route changes, which this slice
is not licensed to make.

## Budget

Alarm when the engagement-detail page load exceeds:

- **> 11 DB statements observed in CP logs** for one request id (today's
  steady state is 10–11). Going over this means a new statement
  appeared; the new statement must be justified or eager-loaded.
- **> 6 outbound HTTP calls from the BFF route to CP** (today's count).
  Any new call added here without justification should fail review.

## Follow-up worth its own slice

- Add a CP-side aggregate route (`/engagements/{id}/detail`) that joins
  engagement + members + matrix in one transaction with `selectinload`
  on the relationship loaders. Cuts CP wall-clock by ~5x the round-trip
  latency between BFF and CP, drops total queries to ~3.
- Add structured `request_id` -> `db_statement_count` logging to CP so
  the alarm budgets above can be enforced automatically rather than
  manually verified.
