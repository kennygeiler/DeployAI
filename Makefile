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

DC := docker compose --env-file $(ENV_FILE) -f $(COMPOSE_FILE)

# Ports — sourced from .env at runtime when it exists; these defaults mirror .env.example.
POSTGRES_PORT ?= 5432
REDIS_PORT ?= 6379
MINIO_API_PORT ?= 9000
FREETSA_STUB_PORT ?= 2020
CONTROL_PLANE_PORT ?= 8000
WEB_PORT ?= 3000

.DEFAULT_GOAL := help

.PHONY: help dev dev-verify dev-down dev-logs compose-smoke env

help:
	@echo "DeployAI local stack — Story 1.7"
	@echo ""
	@echo "Targets:"
	@echo "  make dev            Bring up the full stack + seed"
	@echo "  make dev-verify     Probe every service's health endpoint"
	@echo "  make dev-down       Tear down + remove named volumes"
	@echo "  make dev-logs       Tail compose logs"
	@echo "  make compose-smoke  CI entry point (dev + dev-verify, 30-min ceiling)"
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
	echo "  web → GET /"; \
	curl -fsS "http://localhost:$(WEB_PORT)/" | grep -qi '<html'; \
	echo "  web → GET /admin/runs"; \
	curl -fsS "http://localhost:$(WEB_PORT)/admin/runs" | grep -q 'Admin'; \
	echo "  seed → fixtures.canonical_events row count ≥ 20"; \
	count=$$($(DC) exec -T postgres psql -U $${POSTGRES_USER:-deployai} -d $${POSTGRES_DB:-deployai} -tAc "SELECT COUNT(*) FROM fixtures.canonical_events" | tr -d '[:space:]'); \
	if [ "$$count" -lt 20 ]; then echo "make: seed check failed (events=$$count)" >&2; exit 1; fi; \
	echo "make: all checks green ($$count events seeded)"

dev-down:
	@echo "make: tearing down stack + volumes"
	$(DC) down -v --remove-orphans

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
