# Human operations runbook

Manual steps: secrets, Docker, and commands that are not fully scripted. Full install: [dev-environment.md](./dev-environment.md).

## Monorepo smoke

```bash
pnpm install --frozen-lockfile
pnpm turbo run lint typecheck test build
```

## Control plane — integration tests

Docker must be running.

```bash
cd services/control-plane && uv sync
env PYTEST_ADDOPTS= uv run pytest tests/integration/ -m integration
```

## FOIA CLI — offline revocation list

1. Build a JSON file: `{ "revocations": [ { "deviceId": "<manifest deviceId>", "revokedAtUnixMs": 123 } ] }`.
2. Run: `foia verify --edge-revocation path/to/revoke.json path/to/bundle-dir`

Bundle must include **`createdAtUnixMs`** in `manifest.json` (golden v1 fixtures use `0`).

## FOIA export skeleton (Story 12.2)

```bash
cd apps/foia-cli && go run ./cmd/foia -- export --out ./tmp-export --account my-account [--from 0] [--to 0]
```

## Sparkle / edge releases

If **Story 11.5** is on your branch: see [edge-agent/sparkle-updates.md](./edge-agent/sparkle-updates.md) for signing secrets and S3.
