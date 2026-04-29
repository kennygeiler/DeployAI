# Customer pilot (Epic 15–16)

Operational docs for **hosted** strategist pilots. Planning source: [`_bmad-output/planning-artifacts/epics.md`](../../_bmad-output/planning-artifacts/epics.md) (Epics **15** prerequisites, **16** design partner).

| Doc | Epic story | Purpose |
| --- | ---------- | ------- |
| [session-and-headers.md](./session-and-headers.md) | 15.1 | JWT / headers actor, `DEPLOYAI_STRATEGIST_REQUIRE_TENANT`, dev defaults |
| [oracle-and-digest-pilot.md](./oracle-and-digest-pilot.md) | 16 | Oracle health URL + CP digest/evidence loaders for pilots |
| [hosted-environment.md](./hosted-environment.md) | 15–16 | **Hardening checklist** — identity, CP coupling, loaders, TLS |
| [oauth-from-web.md](./oauth-from-web.md) | 16.2 | M365 OAuth from web → control plane (Bearer / proxy) |
| [tenant-provisioning.md](./tenant-provisioning.md) | 15.2 | Repeatable tenant + test session for CP/web |
| [queue-durability-modes.md](./queue-durability-modes.md) | 15.3 | Single-replica vs CP-backed queues |
| [meeting-presence-pilot-scope.md](./meeting-presence-pilot-scope.md) | 15.4 | Stub vs Graph truth for `/in-meeting` |
| [support-runbook.md](./support-runbook.md) | 15.5 | Triage during a pilot session |
| [phase-0-checklist.md](./phase-0-checklist.md) | 16.6 | **Hosted verification** gate — JWT/tenant/CP loaders/queues/runbook (before visitors) |
| [design-partner-day-playbook.md](./design-partner-day-playbook.md) | 16.6 | Day-of script + retro prompt |
| [examples/pilot-surface.example.json](./examples/pilot-surface.example.json) | 16.4–16.5 | Sample `DEPLOYAI_PILOT_SURFACE_DATA_PATH` payload |

**Product catalog:** [`whats-actually-here.md`](../../whats-actually-here.md) §10 (FDE checklist).

**Strategist UX (Epic 16):** onboarding strip + **`/settings/integrations`** (M365 links, status, disconnect via BFF when JWT cookie present).
