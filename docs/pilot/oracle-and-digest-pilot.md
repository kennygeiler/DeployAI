# Oracle health and digest grounding (pilot)

These paths matter when **`DEPLOYAI_DIGEST_SOURCE=cp`**, **`DEPLOYAI_EVIDENCE_SOURCE=cp`**, or **`DEPLOYAI_PILOT_TENANT_ID`** aligns with the signed-in tenant — see [`hosted-environment.md`](./hosted-environment.md).

## Oracle HTTP liveness

- **Env:** `DEPLOYAI_ORACLE_HEALTH_URL` on **`apps/web`** (see root [`.env.example`](../../.env.example)).
- **Behavior:** `loadStrategistActivityForActor` probes this URL when set; non-OK responses participate in strategist **`agentDegraded`** (Oracle outage banner). When unset, health is **`unconfigured`** and digest/evidence remain readable from canonical sources.

## Digest and evidence from the control plane

- **Morning digest:** `GET /internal/v1/strategist/pilot-surfaces/morning-digest-top` (tenant query param), populated via **`DEPLOYAI_PILOT_SURFACE_DATA_PATH`** on the control plane until canonical projections ship.
- **Evidence deeplink:** `GET /internal/v1/strategist/pilot-surfaces/evidence-node/{node_id}?tenant_id=…`.
- **Sample payload:** [`examples/pilot-surface.example.json`](./examples/pilot-surface.example.json).

## Related

- [`session-and-headers.md`](./session-and-headers.md) — JWT / tenant headers for CP-backed loaders.
- [`meeting-presence-pilot-scope.md`](./meeting-presence-pilot-scope.md) — meeting detection vs Graph staging.
