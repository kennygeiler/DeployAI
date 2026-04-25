# Epic 5 retrospective — Agent runtime foundation

**Date:** 2026-04-25 · **Sprint ref:** `sprint-status.yaml` (epic-5: done)

## Outcomes

- **Python LLM surface:** `packages/llm-provider-py` — Anthropic (Sonnet 4 class) + OpenAI (gpt-4o / embeddings) + `FailoverProvider` (`LLM_PRIMARY_PROVIDER`), 429/5xx retry helper, matrix validation script (`validate:llm-matrix:py` at repo root).
- **Shared runtime:** `services/_shared/runtime` (`deployai-runtime`) — Jinja2 `PromptRegistry`, phase modulator (FR32 weights + alert floors), tool JSON + stub handlers, `docs/prompts/CHANGELOG.md`.
- **Control plane:** migration `20260502_0011` — `tenant_deployment_phases`, `phase_transition_proposals`, `solidification_review_queue`; internal **propose/confirm** phase API; **tiered solidification** classifier (Class A / Class B) with unit + phase integration tests.

## What worked well

- **Path-local packages** via `uv` (`deployai-runtime` in control-plane) avoid another npm boundary for Python services.
- **One migration** for phase + review queue reduced Alembic churn.
- **Failover** as a thin router keeps NFR70 implementation explicit and testable.

## Learnings and risks

- **Anthropic `embed`:** the public Messages API is not a general text-embedding API; we ship **deterministic pseudo-embed** + optional handoff to OpenAI embeddings when `OPENAI_API_KEY` is set—document clearly for vector pipelines.
- **OTel + AWS Secrets (first pass Hardening):** token metrics and `SecretsManager` resolution are now wired in `llm-provider-py` (see package telemetry/secrets modules); full staging validation and exporter config remain ops-owned.
- **Strategist “role”** on phase confirm: internal header only; production needs JWT/scim role checks (documented in route).

## Action items (hardening / follow-up)

| Item | Note |
|------|------|
| **Grafana / OTLP** | Point `opentelemetry` SDK at your collector in k8s; API-only metrics are no-op until SDK + exporter. |
| **KMS/rotation** | `DEPLOYAI_*_SECRET_ARN` pattern documented; align with 90-day rotation runbooks. |
| **Streaming & provider integration tests** | Extended tests for SSE parse + 5xx paths in `llm-provider-py` tests. |
| **Cartographer (Epic 6)** | First story should call `llm-provider-py` + `deployai-runtime` for real extractions. |

## Next handoff (Epic 6)

Build Cartographer/Oracle/Strategist on **`deployai-runtime` + `llm-provider-py` + phase APIs**; no duplicate prompt or state-machine logic in agent folders.
