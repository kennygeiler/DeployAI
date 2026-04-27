# MVP operating plan (2026)

This document turns the **current product risks** into **concrete mitigations**, defines a **usable MVP** (feature-first; **compliance and deep security work explicitly deferred** until after MVP), and sequences work from **today → shippable demo**. It complements the full PRD and `epics.md`; it does not replace them.

**Related:** file-backed board [`../implementation-artifacts/development-board.yaml`](../implementation-artifacts/development-board.yaml) · sprint tracking [`../implementation-artifacts/sprint-status.yaml`](../implementation-artifacts/sprint-status.yaml).

---

## 1. Risks and how we address them

| Risk | Mitigation (owner: whole team) |
|------|---------------------------------|
| **Planning drift** — `sprint-status.yaml` / epics not matching `main` | **Weekly sync (15 min):** compare `main` to board + sprint-status; after merges that ship vertical slices, **same-day** update story rows. **Definition of done** for a PR includes “sprint-status row updated if story state changed.” |
| **Scope creep** — 14 epics / 100+ stories vs. one MVP | This plan’s **MVP scope (§2)** and **out-of-scope (§3)**. **MVP PRs** get priority; new work must map to an MVP line item or a explicitly logged “post-MVP” deferral. |
| **“Operational depth” gap** (observability, runbooks) | **Deferred until after MVP** except one **dev-only** runbook: `make dev` + how to load demo data (link from README). No SLO/chaos/on-call for MVP. |
| **Polyglot tax** (TS / Python / Go / Rust) | **MVP rule:** default changes stay in **web + control-plane** unless another workspace is on the critical path. Edge agent, `foia-cli`, heavy Go/Rust work: **post-MVP** unless blocking local demo. |
| **CI / merge friction** | Addressed in-repo: path-gated required checks use **prep + `paths-filter`** (see [`.github/workflows/README.md`](../../.github/workflows/README.md)). Re-merge **open CI hygiene PRs** so `main` matches the documented pattern. |
| **Compliance / security expectations** (PRD NFRs) | **Explicitly not MVP goals** for this phase: no FOIA packet, no VPAT program, no formal pen-test, no chaos drills. **Keep existing CI** (it does not block “MVP” scope — it’s guardrails you already have); do not expand compliance stories until MVP usability is proven. |

---

## 2. Usable working MVP (definition)

An MVP is **usable** when a **strategist-shaped user** (internal demo) can, on **seeded or dev data**, in one session:

1. **Orient** — Open the app, see **who/what/where** the deployment is (account shell, phase, next actions).
2. **Review** — See a **digest or summary** of what matters (morning or equivalent; mock backend acceptable if the UI and contract are honest).
3. **Track** — See **phase / task** state and that it **updates** from real or demo APIs.
4. **Retrieve** — **Cmd+K** (or equivalent) **memory / evidence search** returns ranked items with a clear path to detail (BFF or mock, but end-to-end in UI).
5. **Trust the loop** — At least one **citation- or evidence-backed** surface (e.g. evidence panel, card with link to source) works without manual JSON.

**Not required for MVP:** production SSO hardening, multi-region, edge capture, in-meeting sub-8s P95, full Oracle tuning, full compliance pack, or customer offboarding.

---

## 3. Out of scope until post-MVP (your ask)

- **Epic 10–12**-style: overrides audit product, **FOIA**, **external auditor**, **immutable S3 Object Lock**, **quarterly compliance**, **NIST RMF** formal pack.
- **Epic 11** (Tauri edge): **V1 MVP is web + API first**; edge agent = later unless you explicitly pivot.
- **Epic 13** (usability + VPAT): optional **one** internal usability pass is allowed; no formal VPAT or third-party audit for MVP.
- **Epic 14** (V1.5 / BYOK / SIEM): deferred.

*Security/compliance in the PRD remain long-term product commitments; this plan only **sequences** work so you can get a **working product slice** first.*

---

## 4. Path from here → MVP (recommended order)

**Track A — Truth & board (week 0, ongoing)**  
- Keep [`development-board.yaml`](../implementation-artifacts/development-board.yaml) statuses current.  
- Reconcile `sprint-status.yaml` with **merged** work (e.g. Cmd+K, strategist shell) the same day as merge.

**Track B — Design system enablers (Epic 7, minimal)**  
Ship only what the MVP surfaces need: **phase indicator, citation/adjacent components, one loading/empty pattern**, and **table/mobile read-only** as needed. Defer “full” Storybook governance / Chromatic / VPAT pipeline until after MVP (see out-of-scope).

**Track C — Strategist “daily loop” (Epic 8)**  
Focus stories in this order: **nav/chrome stability** (if not done) → **digest** → **phase tracking** → **evening synthesis (thin)** → **Cmd+K / memory search** (already on `main` — mark story **done** in sprint-status). **Wire to real or demo APIs**; prefer one honest contract over many mocks.

**Track D — One escalation loop (thin Epic 9)**  
Pick **one** of: **in-meeting-style alert** *or* **action queue** with mock triggers — enough to show “the system interrupts me with the same citation as the digest.”

**Track E — Hardening for “usable” (post-feature)**  
- Remove dead flags / consolidate mock BFF.  
- **E2E smoke** on the golden path (login or dev session → digest → search → one evidence).  
- **Polish** performance only where it blocks the demo (not global perf).

**Rough timeline (indicative, adjust to velocity):**  
- **2–3 weeks:** Tracks A+B+C to “demo walks.”  
- **+2–3 weeks:** Track D + E → **MVP candidate** for an internal or design-partner review.

---

## 5. Planning steps (ritual)

| When | Action |
|------|--------|
| **Each merge** to `main` that completes or advances a story | Update `sprint-status.yaml` (and board row if the item maps). |
| **Weekly** | 15 min: board vs `git log --oneline main -20`; open risks in §1. |
| **Each month** | Re-read this MVP definition; adjust **only** with a short addendum (date-stamped) if scope shifts. |
| **Before “MVP” label** | Run through §2 checklist on seeded data; fix gaps or narrow the MVP claim. |

---

## 6. Success metric (MVP)

**Binary:** a **named internal reviewer** can complete the §2 checklist without a developer in the room, using `docs` + `make dev` (or deployed preview).

**Qualitative:** “I would run my next week’s standup from this” from one product/strategy stakeholder.

---

*Last updated: 2026-04-27*
