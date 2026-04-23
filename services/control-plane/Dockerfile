# Build with: docker build -f services/control-plane/Dockerfile -t deployai/control-plane:dev .
# (from repository root)

FROM python:3.13-slim AS build
ENV UV_LINK_MODE=copy UV_COMPILE_BYTECODE=1 PIP_NO_CACHE_DIR=1
RUN pip install --no-cache-dir uv==0.11.7
WORKDIR /app

# Shared workspace packages must live at paths that match the control-plane's
# `[tool.uv.sources]` declarations (relative `../_shared/<pkg>`), so we mirror
# the monorepo layout inside the image: /app holds control-plane, /_shared
# holds deployai-tenancy (and future siblings).
COPY services/_shared/tenancy /_shared/tenancy

COPY services/control-plane/pyproject.toml services/control-plane/uv.lock services/control-plane/README.md ./
RUN uv sync --frozen --no-install-project --no-dev
COPY services/control-plane/src ./src
RUN uv sync --frozen --no-dev

FROM python:3.13-slim AS runtime
WORKDIR /app
COPY --from=build /app /app
# Editable installs in /app/.venv point at /_shared/tenancy; preserve that tree.
COPY --from=build /_shared /_shared
ENV PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1
EXPOSE 8000
CMD ["uvicorn", "control_plane.main:app", "--host", "0.0.0.0", "--port", "8000"]
