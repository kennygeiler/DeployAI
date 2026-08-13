# Self-serve accounts (email/password, signup, invites)

Status: implemented (branch `account-auth`). Native email/password auth for
DeployAI, layered on the existing session machinery. OIDC (PKCE via Microsoft
Entra) remains the enterprise-SSO option and is untouched — both paths mint
sessions through the same `issue_tokens` service (Redis refresh JTI + RS256
access JWT), so cookies, web middleware, `/auth/refresh` rotation, and logout
behave identically regardless of how a user signed in.

## Flows

### Sign-up (workspace creation)

`POST {CP}/api/v1/auth/signup` `{email, password, workspace_name, display_name}`
— gated by `DEPLOYAI_SELF_SERVE_SIGNUP` (below). Provisions through the same
canonical path as the platform-admin route (`POST /platform/accounts` →
`provision_platform_account`): a new `app_tenants` row with a wrapped tenant
DEK, the empty-canonical-baseline check, and the creator as the tenant's first
user — with roles `["customer_admin"]` and an argon2id credential. Issues a
session immediately (same response shape + `dep_access`/`dep_refresh` cookies
as the OIDC callback) so the web BFF (`POST /api/auth/signup`) can set its
`deployai_access_token` / `deployai_refresh_token` / `deployai_session_tenant`
cookies and land the creator in the app authed.

Web page: `/signup` — rendered only when `NEXT_PUBLIC_SELF_SERVE_SIGNUP=1`,
404 otherwise (mirrors the demo-mode gating style). The page gate is
presentation; the CP env var is the security boundary.

### Sign-in

`POST {CP}/api/v1/auth/login` `{email, password}` (web: `POST /api/auth/signin`
from the `/login` page form). Anti-enumeration posture:

- Unknown email and wrong password return the identical `401` status + body.
- Unknown-email attempts still run one argon2id verify against a dummy hash so
  response timing is uniform.
- Attempt limiting (below) returns a generic `429` either way.

The `/login` page keeps the "View live demo" button (`NEXT_PUBLIC_DEMO_MODE=1`)
and shows the "Sign in with SSO" button when the OIDC envs are configured.

### Password change

`POST {CP}/api/v1/auth/password` `{current_password, new_password}` (authed
bearer; web: `POST /api/auth/change-password`, `/account` page). Verifies the
current password, stores a fresh hash, then revokes **all** refresh sessions
for the user (the session service's per-user JTI index supports enumeration,
but not "all except this one") and mints a replacement pair that the BFF swaps
into the caller's cookies. Honest caveat: outstanding **access** JWTs are
stateless and stay valid until expiry (15 min default) — refresh is what dies.

### Invites

Admin-only (`customer_admin` or `platform_admin` in the JWT roles):

- `POST {CP}/api/v1/auth/invites` `{email, role}` → single-use token, 7-day
  expiry, **SHA-256 hash at rest** (a DB leak cannot redeem invites). Returns
  `join_path` (`/join/<token>`); the web BFF returns `join_url` with the
  deployment's own origin.
- `GET {CP}/api/v1/auth/invites` → pending (unaccepted, unexpired) invites.
- `GET {CP}/api/v1/auth/invites/preview?token=` (public) → email/role/workspace
  for the `/join/[token]` page. Invalid, expired, and used tokens are one
  generic 404.
- `POST {CP}/api/v1/auth/invites/accept` `{token, password, display_name}`
  (public) → creates the user in the invite's tenant with the invite's role,
  marks the invite used, issues a session.

**There is no email delivery anywhere in this stack.** The create endpoint
returns a join link exactly once; the admin copies it from the `/account` page
and sends it out of band. Invitable roles: `customer_admin`,
`deployment_strategist`, `fde`, `biz_dev`, `successor_strategist`,
`customer_records_officer`, `external_auditor` (never `platform_admin`,
`demo_guest`, or `pending_assignment`).

### Account page

`/account` (authed; gated by the web middleware like the other strategist
surfaces): profile (read-only — the only profile-mutation surface today is
SCIM, so there is no display-name edit), change-password form (hidden for
SSO-only users, detected via `has_password` on `GET /api/v1/auth/me`),
sign-out, and the admin invites section. Linked from the top bar ("Account").

## Env gates

| Var | Where | Default | Meaning |
| --- | --- | --- | --- |
| `DEPLOYAI_SELF_SERVE_SIGNUP` | control plane | off | `1` opens `POST /api/v1/auth/signup` (public workspace creation). Enable on the demo deploy; leave off for customer deploys so provisioning stays admin-only. |
| `NEXT_PUBLIC_SELF_SERVE_SIGNUP` | web | off | `1` renders `/signup` and the login-page link. Presentation gate only. |

Login, password change, `/me`, and invites have no gate — they are inert on a
deployment whose users have no password credentials (SSO-only), and invites
require an admin session.

## Password policy

- Length 10–72 characters (72 caps hashing cost; argon2 has no bcrypt-style
  truncation).
- A small embedded worst-passwords blocklist (case-insensitive).
- Deliberately **no** composition rules (NIST 800-63B).

Hashes are argon2id (`argon2-cffi`) with pinned parameters — `time_cost=3`,
`memory_cost=64 MiB`, `parallelism=4` — in
`services/control-plane/src/control_plane/auth/passwords.py`. Hashes are
self-describing, and login rehashes-on-verify when parameters are raised.

## Attempt limiting

Dedicated fixed windows on login / signup / password-change / invite-redeem:
**10 attempts per 5 minutes**, keyed per client IP **and** per identifier,
independent of the global inbound limiter (`DEPLOYAI_API_RATE_LIMIT_PER_MINUTE`,
which defaults to off). Redis-backed when `DEPLOYAI_REDIS_URL` is set; the
fallback is the same single-instance in-memory bucket the global limiter uses
(known limitation: per-process, resets on deploy). Redis loss fails open —
availability over enforcement, with the argon2 verify cost as the residual
brake.

## Audit

Ledger events (tenant-scoped, `engagement_id` null): `account_signup`,
`user_login_succeeded`, `user_login_failed` (known users only —
unknown-identifier failures are log-only because ledger rows are tenant-scoped
and inventing a tenant would leak which emails exist), `password_changed`,
`invite_created`, `invite_accepted`.

## How OIDC coexists

- OIDC users have `password_hash IS NULL`; `/api/v1/auth/me` reports
  `has_password: false` and the account page hides the password form.
- Both paths converge on `issue_tokens` → identical JWT claims, cookies, and
  refresh behavior. The older session endpoints (`/auth/refresh`,
  `/auth/logout`, `/auth/oidc/*`) predate the `/api/v1` prefix and keep their
  paths.
- An email can exist both as an SSO row and (in another tenant) a password
  row; login resolves the oldest **credentialed** row for the email, mirroring
  the OIDC resolver's oldest-row rule.
