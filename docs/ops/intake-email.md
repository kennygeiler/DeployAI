# Inbound engagement email (intake addresses)

Every engagement can mint one intake address, `<slug>-<token>@<intake
domain>` (e.g. `nyc-dot-lidar-h3k9m2p7q1w5e8r4t6y0u2i4@intake.example.com`).
Mail CC'd or forwarded there lands in that engagement as a canonical
`email.thread` event and chains Cartographer extraction, exactly like a
paste on the Capture tab.

Pipeline: mail provider (Postmark) → `POST /internal/v1/intake/email` on
the control plane (JSON, secret header) → address lookup → idempotent
canonical write → extraction → review queue.

Code: `services/control-plane/src/control_plane/api/routes/intake_email_internal.py`
and `services/control-plane/src/control_plane/services/intake_email.py`.
Web surface: the "Or CC the deal address" block on the Capture tab
(`apps/web/src/components/engagements/capture/IntakeAddress.client.tsx`).

## Environment

| Env | Where | Meaning |
| --- | --- | --- |
| `DEPLOYAI_INTAKE_WEBHOOK_SECRET` | control plane | Shared secret the provider sends as `X-DeployAI-Intake-Secret`. **Unset → the webhook endpoint 404s** (feature off; a probe cannot tell disabled from absent). Compared constant-time. |
| `DEPLOYAI_INTAKE_EMAIL_DOMAIN` | control plane | Domain rendered into addresses shown to users (e.g. `intake.example.com`). Unset → the API returns the local part with `email: null` and the web block shows the bare local part. Matching of inbound mail is by local part only, so this is display-only. |

The address read/regenerate API (`GET /internal/v1/engagements/{id}/intake-address`,
`POST …/regenerate`) sits behind the normal internal auth
(`X-DeployAI-Internal-Key` / tenant service tokens) and is only called by
the web BFF. Regenerate is admin-only (customer_admin / platform_admin) —
the BFF enforces the role, the CP trusts its internal caller.

## Postmark setup

1. Create (or reuse) a Postmark **server**, open *Settings → Inbound*.
2. Set the **inbound webhook URL** to the control plane:
   `https://<cp-host>/internal/v1/intake/email`, and add the secret as a
   custom header: `X-DeployAI-Intake-Secret: <value of
   DEPLOYAI_INTAKE_WEBHOOK_SECRET>`. (Postmark supports custom headers on
   the inbound webhook. If your configuration cannot send one, do NOT fall
   back to a secret query parameter — the CP does not accept it; front the
   CP with a proxy that injects the header instead.)
3. Point mail at Postmark for the intake subdomain. Either:
   - **Full inbound domain (recommended):** add an `MX` record for the
     intake subdomain, e.g. `intake.example.com MX 10 inbound.postmarkapp.com`,
     and set that domain as the server's inbound domain. Then set
     `DEPLOYAI_INTAKE_EMAIL_DOMAIN=intake.example.com`.
   - **Address forwarding:** forward a single mailbox to the server's
     `…@inbound.postmarkapp.com` hash address (fine for a pilot; the
     rendered addresses must still use a domain that reaches it).
4. Note the CP endpoint is under `/internal/` — if your ingress blocks
   `/internal/*` from the public internet (it should, for the key-gated
   routes), add an explicit allow for exactly
   `/internal/v1/intake/email`; the route has its own dedicated secret and
   never accepts the internal key as authentication.

Delivery semantics: the webhook answers `200` with `{"dropped": true,
"reason": …}` for anything attributable to the sender (unknown or revoked
address, empty/oversize body, rate limit) — never a 4xx/5xx and never a
bounce, so address validity cannot be probed. Redelivery of the same
`MessageID` to the same engagement dedups (`{"deduplicated": true}`).

## SES alternative (sketch)

Amazon SES inbound can feed the same endpoint with a small adapter:

1. Verify the intake domain in SES, add its `MX` record
   (`inbound-smtp.<region>.amazonaws.com`).
2. Receipt rule → deliver to S3 (raw MIME) → trigger a small Lambda.
3. The Lambda parses the MIME (e.g. Python `email` stdlib), builds the
   Postmark-shaped JSON the CP expects (`ToFull`/`From`/`Subject`/
   `TextBody`/`MessageID`/`Date`) and POSTs it to
   `/internal/v1/intake/email` with the `X-DeployAI-Intake-Secret` header.

The CP contract is just "Postmark-shaped JSON + secret header", so any
provider that can produce that shape works.

## v1 limits (deliberate)

- **Attachments are ignored.** Only `TextBody` (or a naive tag-strip of
  `HtmlBody` when there is no text part) is ingested.
- **500KB body cap.** Larger bodies → `dropped: oversize`.
- **~60 messages/hour per address** (fixed window; Redis-backed when
  `DEPLOYAI_REDIS_URL` is set, else per-instance in-memory). Excess →
  `dropped: rate_limited`; those messages are not retried.
- One active address per engagement; **regenerate revokes the old address
  immediately** — mail to it drops (recognizably `revoked_address` in the
  webhook response, but silently from the sender's perspective).
- Threading is per-message: each accepted delivery is its own
  `email.thread` event (no cross-message conversation stitching like the
  M365/Gmail sync does).

## Audit

Accepted deliveries emit `intake_email_received` ledger rows (source_ref =
the canonical event id); rotations emit `intake_address_regenerated`. Both
are registered in `control_plane/ledger/emitter.py` and bucketed in
`services/engagement_legibility.py`.
