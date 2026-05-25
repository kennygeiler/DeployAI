# OIDC login — local Keycloak + owner provisioning (Phase D inc 1b)

Local development uses **Keycloak** as the OIDC issuer. The compose stack
brings up `keycloak` on `http://localhost:8090` with a pre-imported
realm (`deployai`) and a single confidential client (`deployai-web`).

This document covers two things:

1. The **dev escape hatch** that keeps `apps/web` usable without an OIDC
   round-trip (`DEPLOYAI_LOCAL_DEV_ROLE_INJECT=1`).
2. The **owner provisioning steps** that the actual SSO swap-in needs —
   credentials, env vars, and the order to apply them.

The web callback at `apps/web/src/app/api/auth/callback/oidc/route.ts`
is currently a **stub**:

- Returns **503** `oidc-not-configured` when `DEPLOYAI_OIDC_ISSUER` is
  unset (compose default — no creds yet).
- Returns **501** `oidc-callback-stub-pending-jwt-verify` when the
  issuer IS set but JWT verification is not yet wired (follow-up slice).

The control-plane already implements `/auth/oidc/login` and
`/auth/oidc/callback` (see `docs/auth/sso-setup.md`); this slice
pre-positions the Keycloak issuer + the web-side stub so the swap-in is
mechanical.

## Dev escape hatch — `DEPLOYAI_LOCAL_DEV_ROLE_INJECT`

When `DEPLOYAI_LOCAL_DEV_ROLE_INJECT=1` (set by `infra/compose/docker-compose.yml`
for the local stack), `apps/web/middleware.ts` auto-injects
`x-deployai-role: deployment_strategist` + the seed tenant id so the
strategist surfaces work without an SSO round-trip. Override role via
`DEPLOYAI_DEV_STRATEGIST_ROLE`, tenant via `DEPLOYAI_DEV_TENANT_ID`.

**Never set `DEPLOYAI_LOCAL_DEV_ROLE_INJECT=1` in any hosted / pilot /
prod deploy.** A real SSO proxy or the Keycloak OIDC flow must supply
the headers there.

## Environment variables

Web (`apps/web`):

| Var | Purpose |
| --- | --- |
| `DEPLOYAI_OIDC_ISSUER` | Issuer base, e.g. `http://localhost:8090/realms/deployai`. Stub callback gates on this var being present. |
| `DEPLOYAI_OIDC_CLIENT_ID` | Confidential client id; matches `clients[0].clientId` in `infra/compose/keycloak/realm-export.json` (default `deployai-web`). |
| `DEPLOYAI_OIDC_CLIENT_SECRET` | Confidential client secret. **Owner-provisioned**: Keycloak generates this after admin login; see steps below. |

Control-plane (`services/control-plane`) — same `DEPLOYAI_OIDC_*` vars
plus `DEPLOYAI_OIDC_REDIRECT_URI`; see `docs/auth/sso-setup.md` for the
full list and the production Entra ID flow.

## Owner provisioning — step-by-step

These are the steps the owner runs once Keycloak (or another OIDC
issuer) is reachable. The compose realm is a starting point; production
typically points at a managed IdP (Entra, Google Workspace) using the
same env vars.

1. **Bring up Keycloak**: `make dev` (compose imports the bundled realm).
2. **Sign in to the Keycloak admin console** at
   `http://localhost:8090` with `KEYCLOAK_ADMIN` /
   `KEYCLOAK_ADMIN_PASSWORD` (defaults: `admin` / `admin`).
3. **Open the `deployai` realm** → **Clients** → `deployai-web` →
   **Credentials** tab → copy the **Client secret**.
4. **Set the env vars** in `infra/compose/.env` (or your prod secret
   store):
   ```bash
   DEPLOYAI_OIDC_ISSUER=http://localhost:8090/realms/deployai
   DEPLOYAI_OIDC_CLIENT_ID=deployai-web
   DEPLOYAI_OIDC_CLIENT_SECRET=<paste from step 3>
   ```
5. **Restart the affected services** so the new env is picked up:
   `docker compose -f infra/compose/docker-compose.yml restart web control-plane`.
6. **Verify the stub responds 501** (issuer-present branch):
   `curl -i http://localhost:3000/api/auth/callback/oidc` should return
   `501 Not Implemented` with body `oidc-callback-stub-pending-jwt-verify`.
   A 503 here means the env did not reach the web container.
7. **Create at least one Keycloak user** under realm `deployai` →
   **Users** so the callback handler has something to JIT-provision
   against once it lands.

## Production swap-in (follow-up slice)

When the callback handler is wired:

- Replace the 501 branch with the real token exchange + JWKS verify +
  session-mint chain (the control-plane already has the helpers).
- Point `DEPLOYAI_OIDC_ISSUER` at the production issuer (Entra, Google,
  or a hosted Keycloak — same env shape).
- Drop `DEPLOYAI_LOCAL_DEV_ROLE_INJECT` from any non-local env.

Related: [sso-setup.md](sso-setup.md) (control-plane Entra path) ·
[scim-setup.md](scim-setup.md) (SCIM provisioning) ·
[sessions.md](sessions.md) (cookie + refresh contract).
