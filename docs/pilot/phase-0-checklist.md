# Phase 0 — internal dry-run gate (Epic 16.6)

Run **before** external visitors. Record sign-off (ticket or PR comment) when complete.

| # | Gate | Evidence |
| --- | --- | --- |
| 1 | Hosted web + CP reachable | Health checks green; TLS valid |
| 2 | SSO / JWT | `DEPLOYAI_WEB_TRUST_JWT` + PEM or trusted edge headers; `DEPLOYAI_STRATEGIST_REQUIRE_TENANT` behavior verified |
| 3 | Integrations | At least one M365 path connectable per [`oauth-from-web.md`](./oauth-from-web.md) |
| 4 | Digest slice | `DEPLOYAI_DIGEST_SOURCE=cp` + `DEPLOYAI_PILOT_SURFACE_DATA_PATH` or documented fallback |
| 5 | Evidence slice | `DEPLOYAI_EVIDENCE_SOURCE=cp` + tenant isolation spot-check |
| 6 | Queue mode | Documented per [`queue-durability-modes.md`](./queue-durability-modes.md) |
| 7 | Runbook | [`support-runbook.md`](./support-runbook.md) linked from on-call channel |
| 8 | Limitations | [`whats-actually-here.md`](../../whats-actually-here.md) reviewed with design partner |

## Sign-off template

- **Date:**
- **Environment:**
- **Owner:**
- **Notes / deviations:**
