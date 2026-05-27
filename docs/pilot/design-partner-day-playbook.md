# Phase 1 — design partner day playbook (Epic 16.6)

## Success criteria (same day)

- Deployment strategists can **see tenant context** in-app (onboarding strip + settings).
- **Digest** reflects org data when CP pilot surface or feeds are configured (not silent mock in pilot mode).
- **Integrations** path is understood (connect via CP; proxy/token expectations documented).
- **Rollback**: disable new pilot env flags (`DEPLOYAI_DIGEST_SOURCE`, `DEPLOYAI_EVIDENCE_SOURCE`, `DEPLOYAI_WEB_TRUST_JWT`) and revert to header-only or maintenance page per program decision.

## Data handling

- Use **non-production** or customer-approved pilot tenants only.
- No export of raw tokens in notes; correlation ids only in incident write-ups.

## Who to call

- **Platform / on-call** — see [`support-runbook.md`](./support-runbook.md).
- **Product** — current surface in root [`README.md`](../../README.md) + [`docs/agent-kenny/INDEX.md`](../agent-kenny/INDEX.md); historical scope and known gaps in archived [`deployai-source-of-truth-spec.md`](../archive/product/deployai-source-of-truth-spec.md) §2, §14.

## Retrospective (within 48h)

Capture: what blocked the session, what matched expectations, backlog items. Template: three columns (Start / Stop / Continue) + links to tickets.
