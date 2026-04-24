# DeployAI Control Plane

Story 1.3 scaffold: FastAPI + Pydantic v2 + SQLAlchemy 2.x async + Alembic (empty) + uv-managed deps.

- `GET /healthz` → `{"status": "ok"}` liveness probe.
- Real routes land in later Epic 1 / Epic 5 stories per `_bmad-output/planning-artifacts/architecture.md`.

## Local dev

```bash
uv sync
uv run uvicorn control_plane.main:app --reload
```

## Tests

```bash
uv run pytest
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
