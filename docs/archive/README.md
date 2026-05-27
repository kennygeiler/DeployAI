# Archive — superseded planning documents

Everything in this folder is **historical** and **no longer maintained**. It was
consolidated into the single source of truth on 2026-05-21; further entries were
archived as features were retired or superseded (most recently 2026-05-27 during
the v2 ship doc refresh).

- **Current canonical reference for product spec:** [`docs/product/deployai-source-of-truth-spec.md`](../product/deployai-source-of-truth-spec.md)
- **Current canonical reference for Agent Kenny:** [`docs/agent-kenny/INDEX.md`](../agent-kenny/INDEX.md)
- **Current README (customer / new-engineer landing):** [`../../README.md`](../../README.md)

These files were BMAD-method planning artifacts, earlier product docs, and
docs for retired product lines (edge agent, FOIA CLI). Their claims were
**not re-verified against code** during consolidation — treat them as intent
and history, not as a description of the system. Where any archived file
disagrees with current docs, current docs win.

### Files archived 2026-05-27 during v2 doc refresh

| Path | What it was | Why archived |
| --- | --- | --- |
| [`edge-agent/`](./edge-agent/) | Tauri desktop edge-agent docs (capabilities, platform assessment, Sparkle updates). | The `apps/edge-agent/` source was deleted on 2026-05-23. Product line retired; v2 product captures via paste-in / OAuth ingest, not a desktop agent. |
| [`foia/`](./foia/) | FOIA evidence-bundle format spec. | The `apps/foia-cli/` was deleted on 2026-05-23. FOIA-style export was descoped when the product pivoted from single-strategist GovTech sales to team tool. |
| [`compliance/nist-ai-rmf-mapping.md`](./compliance/nist-ai-rmf-mapping.md) | NIST AI RMF mapping. | Referenced retired Epic 12 stories (FOIA CLI, S3 Object Lock, `/auditor` shell, edge agent). v2 compliance posture lives in `docs/security/`. |
| [`product/deployai-source-of-truth-spec.md`](./product/deployai-source-of-truth-spec.md) | 536-line consolidated pre-v2 product spec. | Pre-v2 framing — references BMAD, edge agent, FOIA, Mr. Oracle, Phase 6.2 labels. Replaced by the post-v2 README + `docs/agent-kenny/` hub. |
| [`human-ops-runbook.md`](./human-ops-runbook.md) | Operator runbook. | 3 of 9 sections covered retired product lines (edge agent, FOIA CLI, Sparkle/appcast). Still-applicable parts now live in `dev-environment.md`, `ops/deployment.md`, and the root `README.md`. |
| [`repo-layout.md`](./repo-layout.md) | Monorepo layout doc. | Listed `apps/edge-agent`, `apps/foia-cli`, `infra/terraform/`, `infra/helm/` — first two deleted, latter two never landed. Replaced by the "Repository layout" section in the root `README.md`. |
| [`delivery-status.yaml`](./delivery-status.yaml) | BMAD-derived epic-level delivery tracker. | Pre-v2. v2 delivery is tracked directly in git + the STATUS table in `docs/agent-kenny/scope-v2.md`. |
| [`dev-environment.md`](./dev-environment.md) | Original dev-bootstrap doc. | Covered the Tauri edge agent + Go FOIA CLI (both deleted 2026-05-23). Replaced by a current, leaner `docs/dev-environment.md`. |

| File | What it was | Why kept |
| --- | --- | --- |
| [`prd.md`](./prd.md) | Product Requirements Document — 79 FR / 78 NFR / 12 design-philosophy commitments. | Requirements baseline and traceability history. |
| [`architecture.md`](./architecture.md) | Intended architecture (AWS/Terraform/ECS/LangGraph/observability). | Target-state design — most of it is unbuilt; see canonical doc §5. |
| [`epics.md`](./epics.md) | 16-epic / ~95-story breakdown with FR→epic mapping. | Story-level history. |
| [`product-brief-DeployAI.md`](./product-brief-DeployAI.md) | Product vision, GTM, commercial model. | Vision and commercial-model history. |
| [`product-brief-DeployAI-distillate.md`](./product-brief-DeployAI-distillate.md) | LLM distillate of the product brief. | History. |
| [`ux-design-specification.md`](./ux-design-specification.md) | UX design specification. | UX intent history. |
| [`mvp-operating-plan-2026.md`](./mvp-operating-plan-2026.md) | MVP sequencing / risk plan. | Planning history. |
| [`implementation-readiness-report-2026-04-21.md`](./implementation-readiness-report-2026-04-21.md) | PRD readiness assessment. | History. |
| [`pm-functionality-and-direction-brief.md`](./pm-functionality-and-direction-brief.md) | PM "what works today" brief. | Merged into the canonical doc. |
| [`whats-actually-here.md`](./whats-actually-here.md) | Fixture-vs-real catalog + demo checklist. | Merged into the canonical doc (§3, §7, §13, §14). |
