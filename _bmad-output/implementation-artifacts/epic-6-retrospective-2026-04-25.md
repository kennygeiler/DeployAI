# Epic 6 retrospective — Cartographer, Oracle & Master Strategist

**Date:** 2026-04-25 · **Scope:** `epics.md` §Epic 6 (stories 6.1–6.8) against current repo

## Outcomes (what shipped in-tree)

- **Cartographer (`services/cartographer`):** `triage` relevance, `extract` + chunked/map-reduce path, `llm_extract`, metrics, benchmark CLI; tests across triage, extract replay, extract branches, stub graph/memory, 100-mixed triage, integration with Postgres; CI-sensitive **ruff** hygiene on `extract` / `llm_extract` / tests (format drift was a recurring smoke failure).
- **Oracle (`services/oracle`):** `retrieve` (phase-gated / marker / null-result patterns per tests), `budget` (3-item + ranked_out), `posture` (suggestions-only); dedicated tests (`test_retrieve`, `test_posture`, etc.).
- **Master Strategist (`services/master_strategist`):** `arbitrate`, phase proposal flow (`test_phase_propose`), `degradation` + tests; internal-only posture preserved in design (no DP10 user-facing MS UI in V1).
- **Control plane glue:** e.g. cartographer extraction persist, **phase transition** integration tests — agents + migrations consume shared **deployment phase** and citation contracts.

## What worked well

- **Clear service boundaries** — each agent is its own `services/<agent>` with tests colocated; Epic 5’s `deployai-runtime` + `llm-provider-py` stay the shared spine without copy-paste prompts in three places.
- **Replay / contract tests** (Cartographer `test_extract_replay`, Oracle invariants) catch regressions before surface work.
- **Triage before extract** (6.1) keeps extraction spend bounded and matches the “mission = phase + objectives” product rule.

## Learnings and risks

- **CI brittleness on Python style:** small **ruff format** drifts in agent tests or generated edges blocked “green” on unrelated PRs; treat `ruff format` on touched files as part of the default agent workflow.
- **Cross-package Docker / path deps** (e.g. control-plane + `llm-provider-py` layout) need the **`/repo` mirror** pattern in Docker so `uv` path deps never escape the sandbox; document for any new workspace path deps.
- **Epic 6 → 7/8 handoff:** agent outputs are citation-enveloped, but **UX consumption** (CitationChip, EvidencePanel, now Phase/Freshness) lands in **Epic 7**; Epic 6 is “engine complete,” not “user complete.”
- **Oracle “surfaces” in copy vs code:** FR34/FR8 Morning Digest *surface* is Epic 8; Oracle enforces **budget + footer** at the agent/contract level first — keep naming aligned in reviews so PM expectations match milestone.

## Action items (forward)

| Item | Owner / note |
| ---- | ------------ |
| **Lock ruff in agent pre-push** | Add Makefile or pre-commit for `uv run ruff check && ruff format` on `services/cartographer`, `services/oracle`, `services/master_strategist` when touched. |
| **E2E slice Oracle → web** | After Epic 7 primitives + Epic 8 shell, one smoke path: “stub Oracle response → Digest row with CitationChip.” |
| **Master Strategist visibility** | Internal metrics/dashboard for arbitration outcomes (deferred) — don’t conflate with user-facing “MS UI” (DP10). |
| **Load / p95 extract** | Story 6.2 AC mentions 5 min p95 for 60-min transcript; keep a scheduled benchmark (nightly or weekly) if not already in CI. |

## Readiness for Epic 7/8

- **Epic 7 (design system):** Citation + evidence + chrome chips can compose agent output without forking styles.
- **Epic 8 (surfaces):** Wire Oracle/Cartographer APIs to Morning Digest / Phase Tracking with shared primitives; **OverrideComposer (7.5)** is the trust-repair prequel to **Epic 10** full override pipeline.

## Team sentiment (brief)

- **Velocity:** High concentration of Python + contract logic; review fatigue on small lint fixes — **automate formatting** where possible.  
- **Pride points:** Triage gating, suggestions-only posture, and arbitration routing are the “safety rail” story customers will feel in prod.
