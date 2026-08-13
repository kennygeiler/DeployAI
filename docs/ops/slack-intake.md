# Slack channel intake (Wave 5 SL1)

Channel-scoped Slack ingestion for DeployAI. The bot's channel membership is
the **consent boundary**; a channel → engagement mapping is the explicit
opt-in that lets DeployAI store the channel's messages.

## Consent model

| State | What DeployAI stores |
| --- | --- |
| Bot **not in** channel | Nothing — Slack never sends us the channel's messages. |
| Bot in channel, **unmapped** | Nothing. Message events are counted (`deployai_slack_unmapped_events_dropped_total`) and dropped. The bot's own `member_joined_channel` event records a *pending channel* row — channel id + name only, never content. |
| Bot in channel, **mapped** to an engagement | Message events accumulate in a staging table, then batch into `slack.thread` canonical snapshot events on the engagement. |
| Mapping **revoked** | Staging stops; unflushed staged messages are deleted. Snapshots already in canonical memory stay — the ledger is append-only by trigger. Re-mapping later is a new consent grant. |

Message edits and deletions (`message_changed` / `message_deleted` subtypes)
are never ingested; a snapshot only changes by being superseded with a new
event when new messages arrive.

## Slack app setup

Create a Slack app (<https://api.slack.com/apps>) for the workspace, or use
this manifest as a starting point (replace the two URLs):

```yaml
display_information:
  name: DeployAI
  description: Channel-scoped engagement intake for DeployAI.
features:
  bot_user:
    display_name: deployai
    always_online: true
oauth_config:
  redirect_urls:
    - https://<control-plane-host>/integrations/slack/oauth/callback
  scopes:
    bot:
      - channels:history # read messages in public channels the bot is in
      - channels:read # channel metadata (names for the settings UI)
      - groups:history # read messages in private channels the bot is in
      - groups:read # private-channel metadata
      - im:history
      - mpim:history
      - users:read
      - team:read
      - chat:write
settings:
  event_subscriptions:
    request_url: https://<control-plane-host>/integrations/slack/events
    bot_events:
      - message.channels # public-channel messages
      - message.groups # private-channel messages
      - member_joined_channel # bot invited → pending channel for the settings UI
  org_deploy_enabled: false
  socket_mode_enabled: false
```

Control-plane environment:

- `DEPLOYAI_SLACK_CLIENT_ID`, `DEPLOYAI_SLACK_CLIENT_SECRET`,
  `DEPLOYAI_SLACK_REDIRECT_URI` — OAuth v2 install flow.
- `DEPLOYAI_SLACK_SIGNING_SECRET` — request-signature verification on
  `/integrations/slack/events`. **Fail-closed**: without it, event callbacks
  are rejected (503). `DEPLOYAI_SLACK_ALLOW_UNSIGNED=1` is a dev-only bypass.

## Install flow

1. Admin/strategist hits `GET /integrations/slack/oauth/connect?tenant_id=…`
   (from Settings → Integrations) and approves the app in Slack. The
   callback stores the bot token, team id, and bot user id on the tenant's
   `integrations` row (`provider = "slack"`).
2. Point the Slack app's Events API request URL at
   `/integrations/slack/events` — the endpoint answers the
   `url_verification` challenge.
3. In Slack, **invite the bot** to each channel to ingest
   (`/invite @deployai`). Each invite surfaces the channel under
   *Settings → Integrations → Slack channel intake* as a pending channel.
4. Map the pending channel to an engagement. From that moment messages are
   staged; until then they are dropped.

## Batching semantics

- Staged messages flush into `slack.thread` canonical snapshot events:
  **per channel per thread** (`thread_ts`) when threaded, else **per channel
  per UTC day**.
- Each snapshot rebuilds the whole unit and fingerprints the sorted message
  timestamps. The `ingestion_dedup_key` is
  `slack:thread:{channel}:{unit}:{fingerprint}:v1`, so:
  - Slack event re-delivery dedups at the staging unique key
    (`tenant, channel, ts`).
  - Re-running the flush on an unchanged unit is a no-op (same fingerprint).
  - New messages in a unit produce a **new** snapshot event superseding the
    old one (append-only; consumers should prefer the latest snapshot per
    channel+unit).
- Snapshot events carry the mapping's `engagement_id`; Cartographer
  extraction chains on each new snapshot (best-effort — an extraction
  failure is reported in the flush response, never blocks the flush).

### Running the flush

`POST /internal/v1/slack/flush?tenant_id=…` (internal key or per-tenant
service token). Run it on a schedule — e.g. a cron hitting each active
tenant every 15–30 minutes. There is no in-process scheduler for it yet;
the event path deliberately never flushes inline so the Slack 3-second ack
window is never spent on LLM calls.

## Internal API surface

| Route | Purpose |
| --- | --- |
| `GET /internal/v1/slack/channel-mappings?tenant_id=…[&include_revoked=true]` | List mappings. |
| `POST /internal/v1/slack/channel-mappings?tenant_id=…` | Create (`channel_id`, `channel_name?`, `engagement_id`, `created_by?`). 409 if the channel is already actively mapped; clears the pending row. |
| `POST /internal/v1/slack/channel-mappings/{id}/revoke?tenant_id=…` | Revoke (idempotent); deletes the channel's unflushed staged messages. |
| `GET /internal/v1/slack/pending-channels?tenant_id=…` | Bot-invited, unmapped channels. |
| `POST /internal/v1/slack/flush?tenant_id=…` | Batch staged → snapshots + extraction. |

BFF (user-facing, Settings → Integrations): `GET/POST
/api/bff/tenant/slack-channels` and `POST
/api/bff/tenant/slack-channels/{id}/revoke`. Reads gate `canonical:read`;
create/revoke gate `ingest:sync` (platform_admin / deployment_strategist /
fde).

## Limits and known gaps

- **Flush scheduling** is external (cron); nothing flushes automatically on
  a threshold yet.
- **Channel renames** are not tracked; the mapping keeps the name captured
  at map time (or the id if the `conversations.info` lookup failed).
- Messages are truncated at 20 000 characters; file/attachment contents are
  not fetched — only the message text.
- One Slack workspace per tenant (team id resolved against the tenant's
  single `provider = "slack"` integration row).
- `im:history` / `mpim:history` scopes are requested for future DM support,
  but DM events are dropped today (no channel mapping can exist for them).
- Pending-channel names come from a best-effort `conversations.info` call at
  invite time; a failure leaves the row with the raw channel id, and the
  settings UI also accepts mapping any channel by id.
