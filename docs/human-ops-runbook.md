# Human operations runbook

Steps a **person** must take that are not fully automated in-repo: secrets, cloud consoles, local toolchain, and optional release paths. For day-to-day dev installs, start with [dev-environment.md](./dev-environment.md).

---

## 1. Monorepo smoke (every PR / local sanity)

| Who | Action |
|-----|--------|
| Engineer | Install Node 24, pnpm, Rust, Go, Python/uv per [dev-environment.md](./dev-environment.md). |
| Engineer | `pnpm install --frozen-lockfile` then `pnpm turbo run lint typecheck test build` from repo root. |
| Engineer | Optional: `pre-commit install` so formatters run on commit. |

**No secrets required** for the default turbo smoke.

---

## 2. Control plane — integration tests (Docker)

| Who | Action |
|-----|--------|
| Engineer | Install and **start Docker Desktop** (or equivalent). |
| Engineer | `cd services/control-plane && uv sync` |
| Engineer | `env PYTEST_ADDOPTS= uv run pytest tests/integration/ -m integration` |

**Why:** Default `pytest` in `pyproject.toml` skips `integration` (no Docker). CI runs integration in a job with Docker available.

**Env:** Tests often need `DEPLOYAI_INTERNAL_API_KEY` only when exercising internal routes from test clients; see individual tests and [control-plane README](../services/control-plane/README.md).

---

## 3. Edge agent — local dev

| Who | Action |
|-----|--------|
| Engineer | `pnpm install` at repo root. |
| Engineer | `pnpm --filter @deployai/edge-agent dev` or `cd apps/edge-agent && pnpm dev` (runs **`tauri dev`**; Vite serves **`http://localhost:1420`** via **`pnpm vite:dev`** from `tauri.conf.json`). |
| Engineer | On macOS, grant **microphone** when prompted; consent flow uses browser `localStorage`. |

**No secrets required** for local dev of UI + Rust commands.

**If dev hangs on “Waiting for frontend on :1420”** or Vite says **port in use**, see [dev-environment.md §5](./dev-environment.md#5-run-each-workspace) — wrong `beforeDevCommand`, stale Vite, or missing **`default-run`** in `Cargo.toml`.

---

## 4. Edge agent — macOS release build (optional)

| Who | Action |
|-----|--------|
| Release engineer | Apple Developer Program membership; **Developer ID Application** cert installed on the build Mac. |
| Release engineer | In GitHub **Actions** → repository **Secrets**, set (names used by [edge-agent-spike.yml](../.github/workflows/edge-agent-spike.yml)): `APPLE_DEVELOPER_ID_APPLICATION`, `APPLE_TEAM_ID`, `APPLE_ID`, `APPLE_APP_SPECIFIC_PASSWORD` for notary steps. |
| Release engineer | Trigger or push to a PR that touches `apps/edge-agent/**` to run **Edge Agent Spike** workflow on `macos-14`. |

If Apple secrets are **missing**, the workflow still builds; the optional notary step is skipped.

---

## 5. Sparkle / appcast — signing & hosting (Story 11.5)

| Who | Action |
|-----|--------|
| Security / platform | Generate a **32-byte Ed25519 seed**; store as GitHub secret **`SPARKLE_PRIVATE_KEY_SEED_B64`** (standard Base64 of those 32 bytes). **Never commit the seed.** |
| Security / platform | Derive the **public** key for operators and for app config: `cd apps/edge-agent/src-tauri && SPARKLE_PRIVATE_KEY_SEED_B64='…' cargo run --release --bin sign-sparkle-archive -- --print-public-key` |
| Security / platform | Set repo **Variable** `APPCAST_DOWNLOAD_BASE_URL` to the HTTPS prefix where DMGs will be hosted (no trailing slash), e.g. `https://releases.example.com/edge-agent`. |
| Release engineer | After CI produces `dist/appcast.xml` + DMG artifacts, ensure the **enclosure URL** in the appcast matches the real file location. |
| Optional S3 | Set secrets `APPCAST_S3_BUCKET`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, and `AWS_DEFAULT_REGION` (or rely on OIDC if you change the workflow). The workflow installs **awscli** on the macOS runner only for that optional step. |

**Spot-check:** Compare one signature from our `sign-sparkle-archive` with Sparkle’s `sign_update` on the same file before trusting production feeds. See [edge-agent/sparkle-updates.md](./edge-agent/sparkle-updates.md).

---

## 6. FOIA CLI (`apps/foia-cli`)

| Who | Action |
|-----|--------|
| Engineer | Install Go 1.26+; `cd apps/foia-cli && go test ./...` |
| Engineer | `go run ./cmd/foia -- verify <bundle-dir>` (options per [bundle-format.md](./foia/bundle-format.md) when extended). |

**No secrets** for offline verify.

---

## 7. Web strategist E2E

| Who | Action |
|-----|--------|
| Engineer | Build production web app; from `apps/web`, `CI=1 pnpm test:e2e` (see root [README](../README.md#quick-start)). |

---

## 8. BMAD / planning artifacts

| Who | Action |
|-----|--------|
| PM / lead | Update [`sprint-status.yaml`](../_bmad-output/implementation-artifacts/sprint-status.yaml) when stories merge. |
| Team | Use `.cursor/skills/` BMAD skills for PRD, stories, reviews (see root README table). |

---

## Quick reference — GitHub secrets & variables (edge releases)

| Name | Type | Purpose |
|------|------|---------|
| `SPARKLE_PRIVATE_KEY_SEED_B64` | Secret | Signs DMG for `sparkle:edSignature` in CI. |
| `APPCAST_DOWNLOAD_BASE_URL` | Variable | Prefix for enclosure URLs in generated `appcast.xml`. |
| `APPCAST_S3_BUCKET` | Secret | Optional S3 bucket for appcast + DMG. |
| `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` / `AWS_DEFAULT_REGION` | Secret | Optional; used with S3 upload step. |
| Apple notary quartet | Secret | Optional codesign + notary on macOS job (see §4). |

---

## When something breaks

| Symptom | Likely human fix |
|---------|------------------|
| Integration tests deselected / 0 ran | Export `PYTEST_ADDOPTS=` and pass `-m integration`; ensure Docker is running. |
| Edge workflow skips signed appcast | Add `SPARKLE_PRIVATE_KEY_SEED_B64` and ensure `tauri build` produced a `.dmg`. |
| `sign-sparkle-archive` not in git | Source is `apps/edge-agent/src-tauri/src/tools/sign_sparkle_archive.rs` (not `src/bin/`, ignored by repo `bin/` rule for Go). |
| pnpm engine error | Switch to Node **24.x** per `.nvmrc`. |
