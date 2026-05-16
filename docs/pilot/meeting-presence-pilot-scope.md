# Meeting presence — pilot scope

**CP contract:** `GET /internal/v1/strategist/meeting-presence?tenant_id=…` (internal key required).

## Current behavior

- **Default:** `in_meeting: false`, `detection_source: off`.
- **Stub tenants:** if `tenant_id` is listed in **`DEPLOYAI_STUB_IN_MEETING_TENANT_IDS`** (comma-separated UUIDs on CP), returns a **deterministic** in-meeting payload (`detection_source` uses `oracle_signal` shape for demos).

**Implementation:** [`strategist_meeting_presence.py`](../../services/control-plane/src/control_plane/api/routes/strategist_meeting_presence.py).

## Pilot messaging

Choose **one** for the design partner brief:

1. **Stub-only Phase 1:** “In-meeting card is **demo-capable** with env allowlist; not your real calendar yet.”
2. **Graph path (future):** implement `graph_cache` or live calendar read—then update this doc and CP response `detection_source`.

## Web dependency

`loadStrategistActivityForActor` calls CP with **`tenant_id=`** derived from the authenticated actor’s tenant UUID (`GET /internal/v1/strategist/meeting-presence?tenant_id=…`). Misaligned actor vs CP stub allowlists yield empty or misleading presence.

When **`DEPLOYAI_PILOT_TENANT_ID`** matches the actor and CP reports **`detection_source: off`**, the strategist shell shows an informational banner (calendar / Graph connector pending). URL demo flags (`?inMeeting=1`) do **not** flip that banner; they only overlay **`inMeeting` UI state** via [`strategist-surface-flags`](../../apps/web/src/lib/epic8/strategist-surface-flags.ts). In **`NODE_ENV=production`** builds, meeting URL overlays are ignored unless **`NEXT_PUBLIC_DEPLOYAI_STRATEGIST_MEETING_URL_DEMO=1`** ([`strategist-url-demo-policy`](../../apps/web/src/lib/epic8/strategist-url-demo-policy.ts)).

## Correlation identifiers (Lane M — meetings / strategist-activity)

Web stamps **`X-DeployAI-Correlation-Id`** on internal CP calls from `loadStrategistActivityForActor`, preferring the inbound **`x-deployai-correlation-id`** request header when middleware provides one ([`correlation-id`](../../apps/web/src/lib/internal/correlation-id.ts)). See [`correlation-ids-rollout.md`](../production/correlation-ids-rollout.md).
