# DeployAI Control Plane

Story 1.3 scaffold: FastAPI + Pydantic v2 + SQLAlchemy 2.x async + Alembic (empty) + uv-managed deps.

- `GET /healthz` → `{"status": "ok"}` liveness probe.
- Routes are implemented under `src/control_plane/api/routes/`; architecture overview in the root [`README.md`](../../README.md) and the Agent Kenny hub at [`docs/agent-kenny/INDEX.md`](../../docs/agent-kenny/INDEX.md). (Pre-v2 source-of-truth spec archived at [`docs/archive/product/deployai-source-of-truth-spec.md`](../../docs/archive/product/deployai-source-of-truth-spec.md) §4.)

## Local dev

```bash
uv sync
uv run uvicorn control_plane.main:app --reload
```

## Tests

```bash
uv run pytest
```

**Line/branch coverage** for `src/control_plane/` (default unit selection only; large service → expect **partial** totals until more integration tests run):

```bash
pnpm run test:cov
```

Default `addopts` skips `integration` and `fuzz` markers (fast unit suite only; matches **smoke** in `ci.yml`).

**Integration tests** (Postgres via testcontainers, **Docker must be running**; same as **Control plane (integration)** in `ci.yml`):

```bash
# Full integration tree (~48 tests; clear addopts so `-m integration` is not pre-deselected)
env PYTEST_ADDOPTS= uv run pytest tests/integration/ -m integration
```

**One file** (optional):

```bash
env PYTEST_ADDOPTS= uv run pytest tests/integration/test_m365_calendar_flow.py -m integration
```

**Fuzz** (slow; separate workflow `fuzz.yml`):

```bash
env PYTEST_ADDOPTS= uv run pytest tests/fuzz/ -m fuzz
```

You may see a `testcontainers` Redis `DeprecationWarning`; it is harmless until upstream updates.

## Telemetry and LLM API keys in production

- **OTel:** The process installs an OpenTelemetry **SDK** `MeterProvider` with **OTLP/HTTP** when
  `OTEL_EXPORTER_OTLP_ENDPOINT` or `OTEL_EXPORTER_OTLP_METRICS_ENDPOINT` is set (and `OTEL_SDK_DISABLED` is
  not true). `deployai-llm-provider-py` then exports `deployai.llm.*` token counters to your collector. See
  [`.env.example`](../../.env.example) for the usual environment variables.
- **Secrets from AWS:** The image already includes **boto3** and uses AWS APIs elsewhere. For
  `DEPLOYAI_ANTHROPIC_SECRET_ARN` / `DEPLOYAI_OPENAI_SECRET_ARN`, grant the task role
  `secretsmanager:GetSecretValue` on the targeted secrets, or use another approved mechanism
  (e.g. EKS/ECS secrets that inject `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` directly and leave ARNs unset).
- **Docker:** The control-plane [Dockerfile](./Dockerfile) copies `packages/llm-provider-py` into the image so
  the `deployai-llm-provider-py` path dependency resolves at build time.
