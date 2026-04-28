# Sparkle-compatible updates (Story 11.5)

The edge agent does **not** embed Sparkle.framework today. Instead, the Tauri shell:

1. Fetches `appcast.xml` over HTTPS (`edge_agent_sparkle_fetch_latest_item`).
2. Parses the first RSS `<item>` / `<enclosure>` (Sparkle convention: newest first).
3. After downloading an update archive, verifies `sparkle:edSignature` with **Ed25519 over the raw file bytes** — matching Sparkle’s `sign_update` / `generate_appcast` behavior (`edge_agent_sparkle_verify_local_archive`).

Applying the update (replace `.app`, relaunch) remains a platform integration task; crypto verification is enforced **before** that step.

## Keys and `Info.plist`

- **Private key:** 32-byte seed, standard Base64, stored in CI as `SPARKLE_PRIVATE_KEY_SEED_B64`.
- **Public key:** 32-byte Ed25519 public, standard Base64. For a **native Sparkle** build, set **`SUPublicEDKey`** in the app bundle’s `Info.plist` to this value. Derive locally with:

  ```bash
  cd apps/edge-agent/src-tauri
  SPARKLE_PRIVATE_KEY_SEED_B64='<same as CI>' cargo run --release --bin sign-sparkle-archive -- --print-public-key
  # (Source lives in `src/tools/sign_sparkle_archive.rs` — not `src/bin/`, which is gitignored as a Go artifact.)
  ```

- The Tauri UI / automation passes the same public key into `edge_agent_sparkle_verify_local_archive` until a compile-time embed (`DEPLOYAI_SPARKLE_PUBLIC_KEY_B64`) is added for releases.

## CI / S3

Workflow: `.github/workflows/edge-agent-spike.yml`.

| Input | Purpose |
|-------|---------|
| `SPARKLE_PRIVATE_KEY_SEED_B64` (secret) | Signs the built `.dmg` after `tauri build`. |
| `APPCAST_DOWNLOAD_BASE_URL` (repo variable) | Prefix for the enclosure URL in `dist/appcast.xml` (no trailing slash). |
| `APPCAST_S3_BUCKET`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_DEFAULT_REGION` (secrets) | Optional: upload `appcast.xml` + DMG to S3. |

If the signing secret is missing, CI copies `public/appcast.xml` to `dist/appcast.xml` (stub).

## Offline / integration checks

- **Linux:** `cargo test updater` (appcast parse + Ed25519 round-trip).
- **macOS CI:** Build DMG → optional sign → `dist/appcast.xml` in artifacts.
- **Manual:** Point the app at a hosted `appcast.xml`, fetch latest item, download DMG, run verify with the known public key.

## Parallel automation tracks

1. **Rust:** verification + HTTP fetch + Tauri commands (`src-tauri/src/updater.rs`).
2. **Release tooling:** `sign-sparkle-archive` binary + `scripts/render-appcast.sh`.
3. **CI:** macOS bundle + optional sign + optional S3; Linux unit tests.
