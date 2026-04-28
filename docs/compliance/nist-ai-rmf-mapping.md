# NIST AI Risk Management Framework — DeployAI mapping

**Document type:** Living mapping (Epic 12 Story 12.8).  
**Version:** 0.1 · **Last reviewed:** 2026-04-26  
**Scope:** Relates product artifacts described in [`whats-actually-here.md`](../../whats-actually-here.md), [`_bmad-output/implementation-artifacts/sprint-status.yaml`](../../_bmad-output/implementation-artifacts/sprint-status.yaml), and planning epics—not every roadmap claim is shipped.

Legend: **Shipped** (in-repo behavior/tests), **Partial** (plumbing or demo-bound), **Planned** (design/epic only).

---

## 1. Govern

| NIST AI RMF subtopics (abbrev.) | DeployAI mapping | Status |
| -------------------------------- | ---------------- | ------ |
| Risk culture / accountability | Role matrix (`deployment_strategist`, `platform_admin`, `external_auditor`, …); Authz resolver TS + Python parity | Partial |
| Oversight of third-party AI | LLM provider abstraction (Epic 1); Oracle/agent contracts (Epics 4–6) | Partial |
| Incident response | Epic 12 operability stories (SLOs, paging, chaos — `12.10`–`12.12` backlog) | Planned |
| Documentation for procurement | Epic 12 Story `12.7` (procurement package), Story `12.6` (quarterly packet) | Planned |

**Citations & overrides (trust):** Override composer + history + personal audit surfaces (Epic 10) map to **governance of human-AI interaction**—reasoning trails retain supersession and private-scope crypto boundaries per citation envelope direction.

---

## 2. Map

| NIST AI RMF subtopics (abbrev.) | DeployAI mapping | Status |
| -------------------------------- | ---------------- | ------ |
| Context & knowledge of AI system | Canonical memory schema; Cartographer/Oracle contracts (Epics 1, 6); strategist loaders | Partial |
| Risk identification | Tenant isolation fuzz CI (Epic 1); integration kill-switch (Epic 2) | Shipped (tests + plumbing) |
| Third-party data | Ingestion pipelines (Epic 3); citation envelope for provenance | Partial |

---

## 3. Measure

| NIST AI RMF subtopics (abbrev.) | DeployAI mapping | Status |
| -------------------------------- | ---------------- | ------ |
| Evaluation / testing | Golden fixtures, replay-parity harness (Epic 4); rule + LLM judges | Partial |
| Human oversight / QA surfaces | Validation & solidification queues (Epic 9); adjudication surfaces | Partial |
| Monitoring | Epic `12.10` SLOs + Grafana + OnCall — backlog | Planned |
| FOIA / evidence export | Go FOIA CLI offline verify (`12.1` done); export skeleton (`12.2` in progress per sprint-status) | Partial |

**Replay-parity gate report** (Epic 4 Story 4.8) ties **measurement** of agent outputs to quarterly compliance reporting (`12.6` planned).

---

## 4. Manage

| NIST AI RMF subtopics (abbrev.) | DeployAI mapping | Status |
| -------------------------------- | ---------------- | ------ |
| Risk prioritization & response | Phase framework & solidification classifier (Epic 5); strategist arbitration (Epic 6) | Partial |
| Incident communication | Break-glass plumbing (Story 2.7 done); end-to-end FR64 (`12.4` backlog) | Partial |
| External auditor access | Story `12.3` (`/auditor` JIT shell — backlog); watermarking & audit logging per epic AC | Planned |
| Immutable audit trail | Story `12.5` (S3 Object Lock audit bucket) — backlog | Planned |

**Edge agent:** Tamper-evident transcripts, offline verification via FOIA CLI, kill-switch poll — Epic 11 (see [`docs/edge-agent/capabilities.md`](../edge-agent/capabilities.md)).

---

## Open gaps (explicit)

1. **Export at scale:** Canonical-memory streaming export, parallel signing, NFR7 load proof — Story `12.2` vs current skeleton (`deployai.foia.export.v0`).
2. **Auditor isolation:** Matrix **denies** `external_auditor` × `canonical:read`; strategist routes and BFF return **403** — Story `12.3` **`/auditor`** shell still backlog (dedicated audit-evidence action TBD).
3. **Break-glass E2E:** Notifications, objection window, SessionBanner on all admin surfaces, transcript delivery — Story `12.4`.
4. **Operational completeness:** SLOs, flags/canary, DR drills — Stories `12.10`–`12.12`.

---

## References

- NIST AI RMF 1.0 — [NIST AI 600-1](https://nvlpubs.nist.gov/nistpubs/ai/NIST.AI.100-1.pdf) (external).
- Internal: [`_bmad-output/planning-artifacts/epics.md`](../../_bmad-output/planning-artifacts/epics.md) Epic 12; PRD cross-references FR60–FR69.
