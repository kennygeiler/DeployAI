# Epic 2 retrospective — Identity, Tenancy & SSO

**Date:** 2026-04-23 · **Sprint ref:** `sprint-status.yaml` (epic-2: done)

## Outcomes

- **Authz and sessions:** `deployai_authz` is integrated end-to-end; tenant-scoped sessions (Redis) and JWT patterns are in production paths.
- **SSO / directory:** Microsoft Entra–compatible OIDC, SCIM 2.0 surface, and account provisioning flow are implemented with integration coverage (`test_scim_flow`, `test_oidc_jit`, `test_account_provision_flow`, `test_session_store_flow`).
- **Operational controls:** Integration kill switch (`test_epic2_kill_switch_and_break_glass.py`) and break-glass session plumbing are test-backed; follow-on UI and notification work stays explicitly scoped out of the plumbing story.

## What worked well

- Reusing a single **integration test harness** (Postgres testcontainers, shared fixtures) made Epic 2 and Epic 3 changes cheap to verify together; CI now runs the full `tests/integration/` tree on every PR to `main`.
- **Clear scope fences** in story docs (e.g. break-glass “plumbing only”) avoided half-built product surfaces.

## Learnings and risks

- **Branch protection** must list every new CI job by exact name (`CI / Control plane (integration)`, etc.); when jobs are added, this doc and `.github/workflows/README.md` should move in lockstep.
- **Path-filtered** workflows (`schema`, `fuzz`, `compose-smoke`) do not run on every PR; admins should configure required checks with GitHub’s “when skipped” behavior in mind, or expect occasional manual judgment on docs-only PRs.
- **Kill switch NFR24** (latency, queue purge) is not fully provable in unit/integration tests alone; staging drills remain valuable before GA.

## Action items (backlog, not blockers)

| Item | Where it lives |
|------|----------------|
| Strategist + ops **UI** for kill switch and break-glass approval flows | Product roadmap / later epic |
| Formal **NFR24** measurement in staging (toggle → token revoke + queue drain) | Ops + observability |
| Tighten **SCIM** / OIDC hardening (rotation, monitoring) as customers onboard | Hardening story when needed |

## Next epic handoff

Epic 3 built on this tenant and auth foundation; Epic 4 (agent runtime / replay) should keep using the same RLS and session assumptions and avoid bypassing `TenantScopedSession` in new code paths.
