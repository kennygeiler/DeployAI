# Build with: docker build -f services/mcp-server/Dockerfile -t deployai/mcp-server:dev .
# (from repository root)

FROM python:3.13-slim AS build
ENV UV_LINK_MODE=copy UV_COMPILE_BYTECODE=1 PIP_NO_CACHE_DIR=1
RUN pip install --no-cache-dir uv==0.11.7
WORKDIR /repo

COPY services/_shared/tenancy /repo/services/_shared/tenancy
COPY services/_shared/citation /repo/services/_shared/citation
COPY services/_shared/authz /repo/services/_shared/authz
COPY services/_shared/runtime /repo/services/_shared/runtime
COPY services/ingest /repo/services/ingest
COPY services/cartographer /repo/services/cartographer
COPY packages/llm-provider-py /repo/packages/llm-provider-py
COPY services/control-plane /repo/services/control-plane

COPY services/mcp-server/pyproject.toml \
     services/mcp-server/README.md \
     /repo/services/mcp-server/
WORKDIR /repo/services/mcp-server
RUN uv sync --no-install-project --no-dev
COPY services/mcp-server/src /repo/services/mcp-server/src
RUN uv sync --no-dev

FROM python:3.13-slim AS runtime
WORKDIR /repo/services/mcp-server
COPY --from=build /repo /repo
ENV PATH="/repo/services/mcp-server/.venv/bin:$PATH" PYTHONUNBUFFERED=1
EXPOSE 3030
CMD ["uvicorn", "mcp_server.main:app", "--host", "0.0.0.0", "--port", "3030"]
