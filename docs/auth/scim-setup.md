# Entra ID SCIM provisioning (DeployAI)

This document describes how to connect Microsoft Entra ID to the control-plane **SCIM 2.0** `/scim/v2` endpoint for user lifecycle (Story 2-3, FR71).

## Endpoint

- **Base URL:** `https://<control-plane-host>/scim/v2`
- **Users resource:** `GET|POST /scim/v2/Users`, `GET|PATCH|DELETE /scim/v2/Users/{id}`

## Authentication

Entra’s SCIM app uses a **long-lived bearer token** (treat as a password).

1. In DeployAI, each customer **tenant** row stores a **SHA-256 hash** of that token in `app_tenants.scim_bearer_token_hash` (the raw token is never stored).
2. Every SCIM request must include:

   `Authorization: Bearer <your-token>`

3. If the token does not match the configured hash, the API returns **401** with a [SCIM error](https://www.rfc-editor.org/rfc/rfc7644#section-3.12) body (`urn:ietf:params:scim:api:messages:2.0:Error`).

**Operational note:** Set the token in your database or provisioning pipeline when onboarding a customer; do not commit secrets to git.

## Microsoft Entra configuration (overview)

1. In Entra, create an **enterprise application** (or use “Provisioning” on an app registration).
2. Set the **Tenant URL** to `https://<host>/scim/v2/`.
3. Set the **secret token** to the value you hashed into `app_tenants` (or generate a random value, store the hash, and hand the clear token to the admin once).
4. **Test connection** in Entra. Entra will issue `GET /scim/v2/Users` to validate the token.
5. Map **attributes** as needed. Supported mapping includes (non-exhaustive): `userName`, `emails[primary]`, `name.givenName`, `name.familyName`, `active`, `externalId`, `roles` (stored as JSON for review).

Group-based assignment is **optional**; this story focuses on **Users**.

## Provisioning operations

- **Create:** `POST /scim/v2/Users` (returns `201` and `Location`).
- **Update:** `PATCH` with [PatchOp](https://www.rfc-editor.org/rfc/rfc7644#section-3.5.2) `Operations` (Entra’s default) is supported, along with a simple merge of top-level fields.
- **Deprovision:** `DELETE /scim/v2/Users/{id}` sets the user to **inactive** and invokes a session-revocation hook (full Redis key deletion is Story **2-4**).

## Filtering and pagination

- `$filter` supports a **subset** of [RFC 7644 filtering](https://www.rfc-editor.org/rfc/rfc7644#section-3.4.2.2), e.g. `userName eq "ada@contoso.com"` and `emails.value eq "ada@contoso.com"`.
- `startIndex` and `count` follow SCIM list conventions (`startIndex` is **1-based**).

## Troubleshooting

| Symptom | Things to check |
|--------|------------------|
| 401 on all calls | Token mismatch; re-verify the SHA-256 of the string Entra sends matches `app_tenants.scim_bearer_token_hash`. No extra spaces in the bearer value. |
| 404 on `GET` user | User id is wrong or belongs to another tenant. |
| 409 on create / patch | Same `userName` or `externalId` already exists for that tenant. |
| Entra “test connection” fails | Health of control-plane, TLS, path must be exactly `/scim/v2/`, and outbound Entra IP allow lists if you use them. |

## Further reading

- [RFC 7643](https://www.rfc-editor.org/rfc/rfc7643) (SCIM core schema) / [RFC 7644](https://www.rfc-editor.org/rfc/rfc7644) (SCIM protocol)
- [Use SCIM to provision users and groups](https://learn.microsoft.com/en-us/entra/identity/app-provisioning/use-scim-to-provision-users-and-groups) (Microsoft)
