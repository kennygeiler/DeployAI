# Story 1.7 — docker-compose reference dev environment.
#
#   make dev          bring up the full local stack (postgres, redis, minio,
#                     freetsa-stub, control-plane, web), wait for healthchecks,
#                     and run the seeder once.
#   make dev-verify   probe every service's health endpoint.
#   make dev-down     tear down + remove named volumes.
#   make dev-logs     tail compose logs.
#   make compose-smoke   CI entry point: dev + dev-verify under a 30-min ceiling.
#   make help         this help.

SHELL := /bin/bash
.SHELLFLAGS := -eu -o pipefail -c

COMPOSE_DIR := infra/compose
COMPOSE_FILE := $(COMPOSE_DIR)/docker-compose.yml
ENV_FILE := $(COMPOSE_DIR)/.env
ENV_EXAMPLE := $(COMPOSE_DIR)/.env.example
SEED_SCRIPT := $(COMPOSE_DIR)/seed/seed.sh

# `env -u ANTHROPIC_API_KEY -u DEPLOYAI_LLM_PROVIDER` — defensive unset so an
# empty shell value (sometimes set by login scripts / oh-my-zsh plugins)
# cannot override the value we load from $(ENV_FILE). Compose precedence is
# shell-env > --env-file; an empty shell var silently zeros out the secret.
# Add new secret-bearing vars to this list when the compose file references them.
DC := env -u ANTHROPIC_API_KEY -u DEPLOYAI_LLM_PROVIDER docker compose --env-file $(ENV_FILE) -f $(COMPOSE_FILE)

# Ports — sourced from .env at runtime when it exists; these defaults mirror .env.example.
POSTGRES_PORT ?= 5432
REDIS_PORT ?= 6379
MINIO_API_PORT ?= 9000
FREETSA_STUB_PORT ?= 2020
CONTROL_PLANE_PORT ?= 8000
WEB_PORT ?= 3000

.DEFAULT_GOAL := help

.PHONY: help dev dev-verify dev-down dev-logs compose-smoke env init seed-app \
	lint-python-epic6-agents format-python-epic6-agents backup restore backup-prune

help:
	@echo "DeployAI local stack — Story 1.7"
	@echo ""
	@echo "Targets:"
	@echo "  make dev            Bring up the full stack + seed"
	@echo "  make dev-verify     Probe every service's health endpoint"
	@echo "  make dev-down       Tear down + remove named volumes"
	@echo "  make dev-logs       Tail compose logs"
	@echo "  make init           First-run install (tenant + LLM + engagement + member). Pass INIT_ARGS or DEPLOYAI_INIT_* env vars. Add --template {gov,healthcare,saas,sales} to seed a vertical bundle."
	@echo "  make seed-app       Seed 1 engagement + ~20 canonical events + run extraction (requires ANTHROPIC_API_KEY in .env)"
	@echo "  make backup         pg_dump + tenant-DEK metadata to S3/MinIO (requires S3_BUCKET; see docs/ops/backup.md)"
	@echo "  make restore        Restore pg_dump from BACKUP=s3://... (requires DEPLOYAI_RESTORE_CONFIRM=YES; see docs/ops/backup.md)"
	@echo "  make backup-prune   Delete S3 backup folders older than BACKUP_RETENTION_DAYS (dry-run unless DEPLOYAI_PRUNE_CONFIRM=YES)"
	@echo "  make compose-smoke  CI entry point (dev + dev-verify, 30-min ceiling)"
	@echo "  make lint-python-epic6-agents  ruff check + ruff format --check (cartographer)"
	@echo "  make format-python-epic6-agents  apply ruff format to the same (before commit)"
	@echo ""
	@echo "Docs: docs/dev-environment.md § Local stack via docker-compose"

env:
	@if [ ! -f "$(ENV_FILE)" ]; then \
		echo "make: creating $(ENV_FILE) from $(ENV_EXAMPLE)"; \
		cp "$(ENV_EXAMPLE)" "$(ENV_FILE)"; \
	fi

dev: env
	@echo "make: bringing up stack (first run may take 5-15 min on cold caches)…"
	$(DC) up -d --build
	@echo "make: waiting for healthchecks…"
	@$(MAKE) --no-print-directory _wait-healthy
	@echo "make: seeding fixtures…"
	@bash "$(SEED_SCRIPT)"
	@echo "make: stack is up. Web → http://localhost:$(WEB_PORT)  |  Control-plane → http://localhost:$(CONTROL_PLANE_PORT)/health"

_wait-healthy:
	@timeout=900; elapsed=0; \
	while :; do \
		statuses="$$($(DC) ps --format '{{.Service}}:{{.Health}}' 2>/dev/null || true)"; \
		unhealthy="$$(echo "$$statuses" | grep -vE ':(healthy|)$$' || true)"; \
		if [ -z "$$(echo "$$statuses" | grep -vE ':healthy$$' || true)" ]; then \
			echo "make: all services healthy"; \
			break; \
		fi; \
		if [ $$elapsed -ge $$timeout ]; then \
			echo "make: timed out waiting for healthchecks after $$timeout s" >&2; \
			echo "$$statuses" >&2; \
			exit 1; \
		fi; \
		sleep 5; elapsed=$$((elapsed + 5)); \
		echo "make: still waiting ($${elapsed}s)…"; \
	done

dev-verify: env
	@echo "make: verifying service health endpoints"
	@set -e; \
	echo "  postgres → pg_isready"; \
	$(DC) exec -T postgres pg_isready -U $${POSTGRES_USER:-deployai} -d $${POSTGRES_DB:-deployai} >/dev/null; \
	echo "  redis → PING"; \
	$(DC) exec -T redis redis-cli ping | grep -q PONG; \
	echo "  minio → /minio/health/live"; \
	curl -fsS "http://localhost:$(MINIO_API_PORT)/minio/health/live" >/dev/null; \
	echo "  freetsa-stub → /health"; \
	curl -fsS "http://localhost:$(FREETSA_STUB_PORT)/health" | grep -q '"status":"ok"'; \
	echo "  control-plane → /health"; \
	curl -fsS "http://localhost:$(CONTROL_PLANE_PORT)/health" | grep -q '"status":"ok"'; \
	echo "  web → GET / (expect 307 → /engagements)"; \
	curl -fsS -o /dev/null -w '%{http_code}\n' "http://localhost:$(WEB_PORT)/" | grep -q '^307$$'; \
	echo "  web → GET /engagements (deployment_strategist header)"; \
	curl -fsS -H "x-deployai-role: deployment_strategist" -H "x-deployai-tenant: 11111111-1111-1111-1111-111111111111" "http://localhost:$(WEB_PORT)/engagements" | grep -qi '<html'; \
	echo "  seed → fixtures.canonical_events row count ≥ 20"; \
	count=$$($(DC) exec -T postgres psql -U $${POSTGRES_USER:-deployai} -d $${POSTGRES_DB:-deployai} -tAc "SELECT COUNT(*) FROM fixtures.canonical_events" | tr -d '[:space:]'); \
	if [ "$$count" -lt 20 ]; then echo "make: seed check failed (events=$$count)" >&2; exit 1; fi; \
	echo "make: all checks green ($$count events seeded)"

dev-down:
	@echo "make: tearing down stack + volumes"
	$(DC) down -v --remove-orphans

# Sprint 1 inc 3 — headless first-run install. CLI mirror of the
# browser /onboarding wizard. Creates tenant + LLM config + first
# engagement + first user + first member, ready for the team to log in.
# Requires the stack to be up (`make dev` first).
#
# Pass values via INIT_ARGS or DEPLOYAI_INIT_* env-vars (see
# `python3 infra/compose/seed/init.py --help`). Example:
#   INIT_ARGS="--tenant-name 'Acme' --llm-provider anthropic \\
#     --llm-api-key $$ANTHROPIC_API_KEY --engagement-name 'Pilot' \\
#     --user-name kenny --role deployment_strategist" make init
init: env
	@echo "make: running first-run install…"
	@python3 $(COMPOSE_DIR)/seed/init.py $(INIT_ARGS)

# Phase 6.2c — repeatable app-schema seed for manual testing.
# Creates one realistic gov/policy engagement w/ ~20 events and triggers
# Cartographer extraction so proposals exist on the engagement detail page.
# Requires the stack to be up (`make dev` first) and ANTHROPIC_API_KEY in
# infra/compose/.env for real LLM proposals (otherwise stub returns empty).
#
# Args: pass `SEED_APP_ARGS=--force-extract` to discard pending proposals and
#       re-run the LLM, or `SEED_APP_ARGS=--skip-extract` to ingest only.
seed-app: env
	@echo "make: seeding app schema (1 engagement + ~20 events + extraction)…"
	@python3 $(COMPOSE_DIR)/seed/seed_app.py $(SEED_APP_ARGS)

# Phase C inc 12.1 — pg_dump + tenant-DEK metadata to S3 (or MinIO).
# Requires the stack to be up. See docs/ops/backup.md for env vars
# (S3_BUCKET is mandatory; S3_ENDPOINT_URL targets MinIO for local dev).
backup:
	@bash scripts/backup.sh

# Phase C inc 12.2 — restore pg_dump from S3 (or MinIO) into Postgres.
# DESTRUCTIVE: overwrites the live DB. Requires DEPLOYAI_RESTORE_CONFIRM=YES
# in the environment; refuses to clobber a non-empty DB unless
# DEPLOYAI_RESTORE_FORCE_OVERWRITE=YES is also set. See docs/ops/backup.md
# § Restore procedure.
restore:
	@if [ -z "$(BACKUP)" ]; then \
		echo "make: BACKUP=s3://bucket/prefix/<TIMESTAMP>/ is required" >&2; \
		exit 2; \
	fi
	@bash scripts/restore.sh "$(BACKUP)"

# Phase C inc 12.3 -- retention sweep for S3 backups written by `make backup`.
# Dry-run by default; set DEPLOYAI_PRUNE_CONFIRM=YES to actually delete.
# Operator runs manually or wires into cron (see docs/ops/backup.md § Retention).
backup-prune:
	@bash scripts/backup-prune.sh

dev-logs:
	$(DC) logs -f --tail=200

# CI entry point — enforces the 30-minute wall-clock ceiling from AC10.
compose-smoke: env
	@echo "make: compose-smoke starting (30-min ceiling)"
	@start=$$(date +%s); \
	$(MAKE) --no-print-directory dev; \
	$(MAKE) --no-print-directory dev-verify; \
	end=$$(date +%s); elapsed=$$((end - start)); \
	echo "make: compose-smoke completed in $${elapsed}s"; \
	if [ $$elapsed -gt 1800 ]; then \
		echo "make: compose-smoke exceeded 30-min budget ($$elapsed s > 1800 s)" >&2; \
		exit 2; \
	fi

# Epic 6 — match pre-commit ruff surface for the Python "agent" services.
# Run from repo root after `uv sync` in each directory (or rely on CI / turbo `lint`).
lint-python-epic6-agents:
	@set -e; for d in services/cartographer; do \
		echo "make: ruff in $$d"; \
		( cd "$$d" && uv run ruff check src tests && uv run ruff format --check src tests ); \
	done
	@echo "make: Epic 6 agent ruff check + format check OK"

format-python-epic6-agents:
	@set -e; for d in services/cartographer; do \
		echo "make: ruff format (write) in $$d"; \
		( cd "$$d" && uv run ruff format src tests ); \
	done
	@echo "make: Epic 6 agent ruff format applied"
