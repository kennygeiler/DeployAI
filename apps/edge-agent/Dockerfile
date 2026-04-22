# Build with: docker build -f apps/edge-agent/Dockerfile -t deployai/edge-agent:dev .
# (from repository root)
#
# This Dockerfile only proves the Rust backend compiles (cargo check) on a clean
# Linux toolchain. Producing a shippable macOS / Windows bundle requires native
# OS runners (code-signing, notarization) and is out of scope for Story 1.3.

FROM rust:1.95-bookworm AS check
RUN apt-get update && apt-get install -y --no-install-recommends \
      libglib2.0-dev libgtk-3-dev libwebkit2gtk-4.1-dev libayatana-appindicator3-dev librsvg2-dev \
      pkg-config \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /src
COPY apps/edge-agent/src-tauri/ ./src-tauri/
WORKDIR /src/src-tauri
RUN cargo fetch
RUN cargo check --locked || cargo check
CMD ["echo", "cargo check ok"]
