# Epic 11 retrospective — Edge capture agent (Tauri macOS V1)

**Date:** 2026-04-26 · **Scope:** Stories **11-1** through **11-7** (per [`sprint-status.yaml`](./sprint-status.yaml)). **Capabilities map:** [`docs/edge-agent/capabilities.md`](../../docs/edge-agent/capabilities.md).

## Outcomes (what shipped in-tree)

- **Shell:** Capability-locked Tauri app with documented [`capabilities.md`](../../docs/edge-agent/capabilities.md), FS/dialog/audio/keychain/http scopes.
- **Crypto & transcripts:** Per-device Ed25519 identity; tamper-evident **v1/v2** transcript bundles (Merkle chain, optional RFC3161, consent hash in v2).
- **Compliance UX:** Two-party consent gate + mic prompt discipline (`TwoPartyConsentDialog`).
- **Updates:** Sparkle-compatible **appcast fetch + local archive verify** (`sign-sparkle-archive`, CI hooks, [`sparkle-updates.md`](../../docs/edge-agent/sparkle-updates.md)).
- **Offline & ops:** `foia verify` golden fixtures + revocation sidecar (Story 11.7); CP kill-switch poll blocks signing when revoked.
- **Dev UI:** Single `App.tsx` exercising CP health, kill-switch refresh, transcript write, audio stub, Sparkle panels — intentional spike surface.

## What went well

- **FOIA pairing:** Edge bundles and CLI verifier advanced together — fewer format mismatches than typical “device vs verifier” splits.
- **Kill-switch + transcript:** Shared revocation semantics across agent and `foia verify --edge-revocation`.
- **CI:** Capability audit script + edge workflows kept permission creep visible.

## Learnings and risks

| Theme | Detail |
| ----- | ------ |
| **Production vs spike** | CoreAudio capture remains **stubbed** for mic gate path; operators must not confuse WebView mic consent with shipped continuous capture. |
| **Merge cadence** | Parallel PRs (Sparkle, kill-switch, FOIA docs) required disciplined merges — format + conflict hygiene (`App.tsx`, `lib.rs`) is recurring tax. |
| **Keychain hardening** | NFR20 note in capabilities: accessibility posture tightening remains follow-up. |

## Action items (forward)

| Item | Home |
| ---- | ----- |
| Real CoreAudio path when product commits | New story under Epic 11 follow-up or Epic 14 **Windows port** prerequisites. |
| Production appcast hosting runbook | [`human-ops-runbook.md`](../../docs/human-ops-runbook.md) §5–6; AWS/GitHub secrets already listed. |

## Parallel longer arc (explicit)

- **Epic 12 (FOIA export / auditor)** continues the **compliance & bundle** line on the repo (`foia export` skeleton → fuller canonical export) — **does not depend** on Epic 11 closure for planning, but shares CLI and docs.
- **Epic 14** tracks **post-V1** platform work (**Windows edge agent**, Helm/BYOK, SIEM egress, etc.) **in parallel** with Epic 12–13 — schedule-driven, not sequential behind Epic 11.

## Readiness handoff

Epic **11** is **closed for scoped V1 macOS capture agent**: signing, transcripts, verifier alignment, updates verification path, and CP revocation gate are in-tree. Further scope belongs to **Epic 12+** or **Epic 14** per product priority.
