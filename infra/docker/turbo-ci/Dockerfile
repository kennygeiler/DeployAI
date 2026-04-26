# CI-parity image: Node 24 (pnpm) + uv + Go 1.26 (foia-cli). Not a production runtime.
# Build:  docker build -f infra/docker/turbo-ci/Dockerfile -t deployai-turbo-ci:local .
# Run:     docker run --rm -v "$PWD":/repo -w /repo deployai-turbo-ci:local
FROM golang:1.26-bookworm AS gobase

FROM node:24-bookworm-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates curl git \
  && rm -rf /var/lib/apt/lists/*

COPY --from=gobase /usr/local/go /usr/local/go

ENV UV_VERSION=0.11.7
RUN curl -LsSf "https://astral.sh/uv/${UV_VERSION}/install.sh" | sh
# Single PATH: Go binaries + uv (install script uses ~/.local/bin) + base image PATH.
ENV PATH="/usr/local/go/bin:/root/.local/bin:${PATH}"

WORKDIR /repo
CMD ["bash", "scripts/ci-turbo-full.sh"]
