# DeployAI Dev Environment Bootstrap (5-minute setup)

Story 1.3 lands the full polyglot stack. Running any workspace locally now requires Node.js + pnpm, Rust, Go, Python, and a handful of small helpers.

## 1. Install the runtimes

Pin versions match the repo files (`.tool-versions`, `rust-toolchain.toml`, `.python-version`, `apps/foia-cli/go.mod`). Homebrew is the sanctioned macOS path; Linux users can swap in `apt`, `asdf`, `rustup`, etc.

```bash
# Node 24 + pnpm 10 (if not already done in Story 1.1)
brew install node@24
corepack enable && corepack prepare pnpm@10.33.0 --activate

# Python 3.13 + uv (for services/control-plane)
brew install python@3.13 uv

# Go 1.26 (for apps/foia-cli)
brew install go

# Rust 1.95 via rustup (for apps/edge-agent)
brew install rustup
rustup toolchain install 1.95.0 --profile minimal -c rustfmt -c clippy
rustup default 1.95.0

# Quality-of-life
brew install pre-commit
```

Verify everything is on PATH:

```bash
node --version       # v24.x
pnpm --version       # 10.33.x
python3.13 --version # 3.13.x
uv --version         # 0.11.x
go version           # go1.26.x
rustc --version      # 1.95.0
```

## 2. Install workspace dependencies

```bash
# Node workspaces (apps/web, apps/edge-agent, apps/foia-cli wrapper, services/control-plane wrapper)
pnpm install

# Python virtualenv for services/control-plane
cd services/control-plane && uv sync && cd -

# Rust build deps fetched on first cargo invocation
cd apps/edge-agent/src-tauri && cargo fetch && cd -

# Go modules fetched on first build
cd apps/foia-cli && go mod download && cd -
```

## 3. Install pre-commit hooks (one-time)

```bash
pre-commit install
```

This wires `.pre-commit-config.yaml` into `.git/hooks/pre-commit` so that formatters (prettier, ruff-format, gofmt, cargo fmt) and lightweight linters (ruff, go vet) run automatically on staged files.

## 4. Verify the smoke suite

```bash
pnpm turbo run lint typecheck test build
```

Should report `20 successful, 20 total` across `@deployai/web`, `@deployai/edge-agent`, `@deployai/foia-cli`, `@deployai/control-plane`, and the `packages/design-tokens` / `build-storybook` fan-out added in Stories 1.4–1.5. Anything less means one of the toolchains above is missing or a version drifted.

## 4a. Verify the accessibility gate stack (Story 1.6)

The four a11y gates that `.github/workflows/a11y.yml` runs can be exercised locally. See [`docs/a11y-gates.md`](./a11y-gates.md) for the full "what each runner catches" + appeal-process reference. Quick commands:

```bash
# Static lint (fastest — matches CI job 1)
pnpm --filter @deployai/web lint

# Storybook per-story axe (matches CI job 2)
pnpm --filter @deployai/web build-storybook
pnpm dlx http-server apps/web/storybook-static --port 6006 --silent &
pnpm --filter @deployai/web storybook:test

# Playwright E2E + axe (matches CI job 3) — needs Playwright browsers:
pnpm --filter @deployai/web exec playwright install --with-deps chromium
pnpm --filter @deployai/web build
pnpm --filter @deployai/web test:e2e

# pa11y-ci (matches CI job 4) — needs puppeteer Chrome:
node node_modules/.pnpm/@puppeteer+browsers@2.13.0/node_modules/@puppeteer/browsers/lib/cjs/main-cli.js \
  install chrome@147.0.7727.57 --path "$HOME/.cache/puppeteer"
pnpm --filter @deployai/web build
pnpm --filter @deployai/web exec next start --port 3000 &
pnpm --filter @deployai/web test:a11y
```

`@axe-core/react` also logs violations to the browser console when running `pnpm --filter @deployai/web dev` — no setup required, tree-shaken out of prod builds.

## 5. Run each workspace

```bash
pnpm --filter @deployai/web dev               # Next.js on :3000
pnpm --filter @deployai/edge-agent dev        # Tauri dev window (requires Rust)
pnpm --filter @deployai/control-plane dev     # FastAPI on :8000 (uvicorn --reload)
pnpm --filter @deployai/foia-cli build && apps/foia-cli/bin/foia
```

## 6. Docker sanity check (optional, Story 1.7 will wire these into docker-compose)

```bash
docker build -f apps/web/Dockerfile -t deployai/web:dev .
docker build -f apps/foia-cli/Dockerfile -t deployai/foia-cli:dev .
docker build -f services/control-plane/Dockerfile -t deployai/control-plane:dev .
# apps/edge-agent Dockerfile only does `cargo check` — shippable bundles need native OS runners.
```

## Troubleshooting

| Symptom | Fix |
|---|---|
| `pnpm install` complains about frozen lockfile | `pnpm install --no-frozen-lockfile` once after pulling a branch that changed deps. |
| `tsc` fails with `exactOptionalPropertyTypes` errors on `vitest.config.ts` | Already excluded in each workspace `tsconfig.json`. If reintroduced, add to the `exclude` array. |
| `uv run pytest` can't find `control_plane` | Run from `services/control-plane/` (or `cd` there first). `pyproject.toml` sets `pythonpath = ["src"]`. |
| `cargo check` wants webkit libs on Linux | `sudo apt install libwebkit2gtk-4.1-dev libgtk-3-dev libayatana-appindicator3-dev librsvg2-dev pkg-config`. |
