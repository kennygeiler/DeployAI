# OAuth from the strategist web app (Microsoft 365)

Epic 16.2: users start M365 connection from **`/settings/integrations`** using links to the **control plane** OAuth routes (calendar, mail, teams).

## Why the browser must hit the control plane

OAuth **PKCE state** and integration cookies are set on the **control plane** host (`Set-Cookie` with path `/integrations/...`). Starting OAuth via a server-side `fetch` from Next.js does not attach those cookies to the user’s browser, so the flow must begin with a **full browser navigation** to the CP `connect` URL.

## Authorization on `connect`

Control plane routes such as `GET /integrations/m365-calendar/connect` require a **valid Bearer access token** (`Authorization: Bearer …`) with a V1 role allowed for `ingest:sync` on the target tenant (see [`integrations_m365_calendar.py`](../../services/control-plane/src/control_plane/api/routes/integrations_m365_calendar.py)).

The static `<a href="...">` links on `/settings/integrations` **do not** attach that header. Pilot deployments typically use one of:

1. **Same-site session** — user signs in to the control plane (OIDC) in the same browser session before clicking Connect; CP session satisfies `bearer_auth_actor` if your deployment maps session to JWT (productized in a later story), **or**
2. **Reverse proxy** — edge forwards `Authorization: Bearer` from the web app’s `deployai_access_token` cookie (or IdP token) to CP paths under `/integrations/`, **or**
3. **Manual / operator** — operators run connect from Swagger or curl with a token during early pilot (document in runbook).

Do **not** pass long-lived tokens in query strings.

## Return URL

`return_to` on connect must be an **absolute** `http(s)` URL (validated in CP). The web app builds it from `x-forwarded-proto` / `x-forwarded-host` (see `getPublicOriginFromHeaders`).

## Disconnect

`POST /api/bff/integrations/{id}/disable` forwards the user’s **access token cookie** to `POST /integrations/{id}/disable` on the control plane. Requires `integration:kill_switch` (deployment strategist and related roles per authz matrix).
