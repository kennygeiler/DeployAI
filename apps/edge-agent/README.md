# DeployAI Edge Agent (`@deployai/edge-agent`)

macOS **Tauri 2** desktop app for tamper-evident capture + verification flows (see [**docs/edge-agent/capabilities.md**](../../docs/edge-agent/capabilities.md)).

## Local development

From repo root:

```bash
pnpm --filter @deployai/edge-agent dev
```

This runs **`tauri dev`**. The Tauri **`beforeDevCommand`** starts **Vite** on **`http://localhost:1420`** via **`pnpm vite:dev`** (do **not** point `beforeDevCommand` at **`pnpm dev`** — it would recurse). Frontend-only:

```bash
pnpm --filter @deployai/edge-agent vite:dev
```

Rust **`Cargo.toml`** sets **`default-run = "deployai-edge-agent"`** because the crate ships two binaries (the app and **`sign-sparkle-archive`**).

**Troubleshooting:** [docs/dev-environment.md §5 — Run each workspace](../../docs/dev-environment.md#5-run-each-workspace) and the **Troubleshooting** table (port **1420**, `cargo run` binary selection).

## Docs

| Topic | Location |
|-------|----------|
| Capability matrix + commands | [docs/edge-agent/capabilities.md](../../docs/edge-agent/capabilities.md) |
| Sparkle / appcast updates | [docs/edge-agent/sparkle-updates.md](../../docs/edge-agent/sparkle-updates.md) |
| Operator secrets & releases | [docs/human-ops-runbook.md](../../docs/human-ops-runbook.md) |
