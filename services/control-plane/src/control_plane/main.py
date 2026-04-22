"""FastAPI entrypoint for the DeployAI Control Plane.

Story 1.3 ships only a liveness endpoint. Real routes land in Epic 1
Stories 1.9+ (tenant isolation, authz) and Epic 5 (compliance + audit).
"""

from __future__ import annotations

from fastapi import FastAPI

app = FastAPI(title="DeployAI Control Plane", version="0.0.0-scaffold")


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    """Liveness probe used by docker-compose (Story 1.7) and the CI smoke test."""
    return {"status": "ok"}
