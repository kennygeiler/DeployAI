# Epic 4 retrospective — Agent runtime contracts & replay-parity

**Date:** 2026-04-25 · **Sprint ref:** `sprint-status.yaml` (epic-4: done)

## Outcomes

- **Citation + retrieval boundary:** `packages/llama-citation-adapter` enforces citation envelope parsing with explicit failures on bad metadata; metrics export aligned with contract checks.
- **Harness:** `apps/eval` delivers rule-based and LLM-judge (Anthropic) paths, golden corpus at scale (`tests/golden/`), and `release-gate` workflow for `golden:validate` + replay-parity smoke.
- **Human loop:** `adjudication_queue_items` in the control plane + `/admin/adjudication` in `apps/web` (authz `eval:view_adjudication`) close the 4-7 data-plane loop for disputes.
- **Tooling:** Root scripts and `docs/prompts/CHANGELOG` discipline for prompt changes (tied to Story 4-6 expectations).

## What worked well

- **End-to-end path** from contract package → eval → CI gate made regressions in fixtures visible early (`golden:validate` matrix).
- **Internal API pattern** (shared internal key) reused for adjudication, consistent with ingestion runs.
- **Stub vs live judge** via `DEPLOYAI_EVAL_JUDGE_MODE` kept CI green while allowing Anthropic runs locally.

## Learnings and risks

- **Branch naming drift:** the feature branch outgrew the “4-2 only” label as Epic 4+5 landed together—use either stacked PRs or **rename the branch** when scope expands (see handoff note in README/PR).
- **LLM judge cost/keys:** live mode requires `ANTHROPIC_API_KEY`; production should prefer **secret ARN + rotation** (addressed in Epic 5 hardening for the shared Python package).
- **Adjudication UI** is a shell until product wires dispute intake from eval runs; backlog remains for automation from `rules-report` / `judge-report` diffs.

## Action items

| Item | Note |
|------|------|
| Wire adjudication from eval diff reports | When automation story is scheduled |
| Keep golden corpus generation reproducible | `golden:author` / `expand-corpus` in CI if drift appears |

## Next handoff (Epic 5 → 6)

Epic 5 (runtime foundation) is delivered in-tree; **Epic 6** agents should consume the same `deployai-runtime` prompts, `llm-provider-py` providers, and **phase** context from the control plane without re-deriving contracts.
