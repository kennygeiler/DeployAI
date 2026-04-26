# `Dockerfile.turbo-all`

Single image with **Node 24** (corepack pnpm 10.33), **Go 1.26** (for `apps/foia-cli`), and **uv 0.11.7** (all `uv.lock` trees via `scripts/ci-uv-sync-all.sh`), matching the [GitHub Actions `smoke` job](.github/workflows/ci.yml).

Rust (`cargo` for Tauri) is *not* in this image: `edge-agent` smoke only runs `tsc` + Vite, same as CI.

## Usage

```bash
docker build -f infra/docker/Dockerfile.turbo-all -t deployai-turbo-all .
docker run --rm -v "$PWD":/repo -w /repo deployai-turbo-all
```

Override the command to run a subset:

```bash
docker run --rm -v "$PWD":/repo -w /repo deployai-turbo-all \
  /bin/bash -lc "bash scripts/ci-uv-sync-all.sh && pnpm turbo run build --filter=@deployai/web..."
```

Apple silicon: if `go` layer fails, build with `docker buildx build --platform linux/amd64 ...` or add an arm64 Go tarball variant.
