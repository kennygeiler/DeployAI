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

Default `addopts` skips `integration` and `fuzz` markers. To run Docker-backed tests (Postgres testcontainer), e.g. M365 calendar flow:

```bash
env PYTEST_ADDOPTS= uv run pytest tests/integration/test_m365_calendar_flow.py -m integration
```
