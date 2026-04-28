# Edge Agent — Tauri capabilities (Story 11.1)

This document maps each declared capability in `apps/edge-agent/src-tauri/tauri.conf.json` to its purpose and scope. Capability identifiers match the Epic 11 Story 11.1 acceptance criteria.

## `default`

- **Purpose:** Core shell behavior (windows, events, app metadata) via `core:default`.
- **Scope:** Main window only; no filesystem, dialog, shell, or HTTP plugin surface.

## `fs:local-only`

- **Purpose:** Persist transcripts, caches, and other app data under the OS app-local data location.
- **Scope:** `fs:allow-applocaldata-*` (meta, read, write, recursive) only — Tauri’s `$APPLOCALDATA` / application-support style paths for this bundle, not arbitrary user paths or full home directory.

## `dialog:file-select`

- **Purpose:** Let the user explicitly pick files or save locations through native dialogs.
- **Scope:** `dialog:allow-open` and `dialog:allow-save` only (no `dialog:default` / message boxes bundled into this capability).

## `audio:capture`

- **Purpose:** Microphone access for local capture after OS and in-app consent.
- **Scope:** Implemented with WebView `getUserMedia` plus `NSMicrophoneUsageDescription` in `src-tauri/Info.plist`. This capability carries **no extra plugin permissions** so the trust boundary stays OS + web APIs; two-party consent UX is expanded in Story 11.4.

## `keychain:read-write`

- **Purpose:** Store per-device keys and secrets in the macOS Keychain (Epic 11 signing stories).
- **Scope:** Rust-only via the `keyring` crate and allowlisted Tauri commands. **Story 11.2:** `edge_agent_signing_identity` / `edge_agent_register_with_control_plane` persist a **32-byte Ed25519 signing seed** (Base64) under service `app.deployai.edge-agent` / account `ed25519-signing-key-v1`. **Story 11.3:** `edge_agent_write_transcript_bundle` writes `deployai.edge.transcript.v1` under app-local `transcripts/<uuid>/` (`segments.json`, `manifest.json`, `transcript.sig`) with a SHA256 Merkle chain over segments, optional RFC3161 via `DEPLOYAI_EDGE_TSA_URL` (default `https://freetsa.org/tsr`). **NFR20 note:** today this uses the `keyring` default accessibility; tightening to `kSecAttrAccessibleWhenPasscodeSetThisDeviceOnly` is a documented hardening follow-up. Spike command `keychain_roundtrip` remains for diagnostics.

## `http:api-only`

- **Purpose:** Reach the DeployAI control plane for health checks and **device registration**.
- **Scope:** Rust-only `reqwest` (`control_plane_health`, `edge_agent_register_with_control_plane` → `POST /internal/v1/edge-agents/register` with `X-DeployAI-Internal-Key`). No `tauri-plugin-http` exposure to the UI. URL allowlist hardening is still recommended before production.

## CI audit

`apps/edge-agent/scripts/audit-capabilities.mjs` runs in CI to ensure required capabilities stay declared and that forbidden broad grants (e.g. `fs:all`, `fs:default`) do not appear in any enabled capability file.
