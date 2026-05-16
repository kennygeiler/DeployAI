# Headless engineering agent workspace (Aider + Git + Node + Python).
# Build: docker build -f infra/autonomous-worker/Dockerfile -t deployai/autonomous-aider .
# Run: docker run --rm -v "$PWD:/workspace" -w /workspace deployai/autonomous-aider \
#   infra/autonomous-worker/execute-task.sh /workspace/plan.md

FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive
ENV LANG=C.UTF-8

RUN apt-get update \
  && apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
    git \
    python3 \
    python3-pip \
    python3-venv \
  && curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
  && apt-get install -y --no-install-recommends nodejs \
  && pip3 install --break-system-packages --no-cache-dir aider-chat \
  && rm -rf /var/lib/apt/lists/*

WORKDIR /workspace

# Default shell: execute-task.sh is intended as the container command.
CMD ["/bin/bash"]
