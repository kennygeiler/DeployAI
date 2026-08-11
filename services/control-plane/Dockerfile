# Build with: docker build -f services/control-plane/Dockerfile -t deployai/control-plane:dev .
# (from repository root)
#
# `uv` resolves `[tool.uv.sources]` relative to this package (`services/control-plane`). Paths like
# `../_shared/*` and `../../packages/llm-provider-py` must exist *without* `..` escaping the project
# root; otherwise `uv sync` errors ("cannot normalize a relative path beyond the base directory").
# We mirror the monorepo under `/repo/...` and set WORKDIR to `/repo/services/control-plane`.

FROM python:3.13-slim AS build
ENV UV_LINK_MODE=copy UV_COMPILE_BYTECODE=1 PIP_NO_CACHE_DIR=1
RUN pip install --no-cache-dir uv==0.11.7
WORKDIR /repo

COPY services/_shared/tenancy /repo/services/_shared/tenancy
COPY services/_shared/citation /repo/services/_shared/citation
COPY services/_shared/authz /repo/services/_shared/authz
COPY services/_shared/runtime /repo/services/_shared/runtime
COPY services/_shared/ingestlib /repo/services/_shared/ingestlib
COPY packages/llm-provider-py /repo/packages/llm-provider-py

COPY services/control-plane/pyproject.toml \
     services/control-plane/uv.lock \
     services/control-plane/README.md \
     /repo/services/control-plane/
WORKDIR /repo/services/control-plane
RUN uv sync --frozen --no-install-project --no-dev
COPY services/control-plane/src /repo/services/control-plane/src
RUN uv sync --frozen --no-dev
# Alembic config + migration scripts — needed so the image can run
# `alembic upgrade head` (see the compose `migrate` service).
COPY services/control-plane/alembic.ini /repo/services/control-plane/alembic.ini
COPY services/control-plane/alembic /repo/services/control-plane/alembic

FROM python:3.13-slim AS runtime
WORKDIR /repo/services/control-plane
COPY --from=build /repo /repo
COPY services/control-plane/docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh
ENV PATH="/repo/services/control-plane/.venv/bin:$PATH" PYTHONUNBUFFERED=1
EXPOSE 8000
# Role/migration dispatch (Railway has no release command or process
# groups); with no SERVICE_ROLE/RUN_MIGRATIONS set this is the old CMD.
ENTRYPOINT ["docker-entrypoint.sh"]
