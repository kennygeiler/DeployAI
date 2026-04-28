# Pilot (single tenant): phased roadmap aligned to `epics.md`

**Document type:** BMAD alignment — maps **operational pilot phases** (closing the loop: ingestion → graph → agents → strategist surfaces) to **`_bmad-output/planning-artifacts/epics.md`** with an honest **built vs pilot‑truth** read.

**Authority:**

| Source | Role |
|--------|------|
| [`epics.md`](../planning-artifacts/epics.md) | Full FR/NFR story grid and acceptance criteria |
| [`sprint-status.yaml`](./sprint-status.yaml) | Story rows marked **done** / **review** / **backlog** on `main` |
| [`whats-actually-here.md`](../../whats-actually-here.md) | **Fixture vs durable APIs**, BFF mocks, demo flags |
| [`epic-8-implementation-status.md`](./epic-8-implementation-status.md) | Epic **8** spec deltas vs shipped skeleton |

**Important:** **`sprint-status.yaml` “done”** means scoped stories merged — **not** automatically “one pilot tenant receives novel operational intelligence end‑to‑end daily.” That stronger claim requires **`whats-actually-here`** honesty plus pilot‑specific verification.

---

## Epic anchors already defined for pilots

`epics.md` **Epic List** explicitly introduces:

- **Epic 15 — Customer Pilot Prerequisites** — hosted identity/durability/meeting‑presence honesty/runbooks; **gates** external pilot work.
- **Epic 16 — Design Partner Pilot** — onboarding, integrations UX, **CP‑backed loaders** replacing mocks/`STRATEGIST_*` URLs (vertical slices: digest + evidence minimum, etc.); sequenced **after** Epic 15 completions or **written waivers**.

Those epics are the **closest canonical mapping** for “one pilot tenant” — the phased plan below **folds into** Epic **15**/**16** while naming **upstream dependencies** (Epic **3**, **6**, **8**, **9**) where the loop breaks if only UI exists.

---

## Phase map: pilot milestone → primary epics & stories

### Phase 0 — Freeze pilot scope (tenant slice + surfaces)

| Intent | `epics.md` alignment | Built on `main`? | Pilot‑truth notes |
|--------|----------------------|------------------|-------------------|
| Single tenant ID, SSO story, success metrics | **Epic 15** — **15.1–15.2**; **Epic 16** — **16.6** (Phase 0 dry‑run + Phase 1 playbook) | **Done** in sprint-status | Repeatable **tenant provisioning** and **playbook** exist; **production SSO** beyond dev middleware — confirm per tenant (**Epic 2** stories **2.2**–**2.4**). |

**Stories to cite:** **15.1**, **15.2**, **16.6**.

---

### Phase 1 — Ingestion → canonical graph authoritative for that tenant

| Intent | `epics.md` alignment | Built on `main`? | Pilot‑truth notes |
|--------|----------------------|------------------|-------------------|
| Mail/calendar/Teams/uploads → immutable events | **Epic 3** — Stories **3.1–3.8** (M365 calendar, email, Teams transcript, upload, thread unit, idempotency, backpressure, `/admin/runs`) | **Epic 3: done** (all listed stories) | [`deferred-work.md`](./deferred-work.md) **Epic 3 follow‑ups**: e.g. **real ASR** for uploads may remain stub — pilot must **scope** which sources are “truth” vs demo. |
| Integrations UX → CP OAuth lifecycle | **Epic 16** — **16.2**, **16.3** | **done** | Pilot validates **connect / status / reconnect / disconnect** for **their** tenant — prerequisite before loaders see live mail/calendar evidence. |
| Schema + isolation | **Epic 1** — **1.8**, **1.9**, **1.10** | **done** | Fuzz/RLS posture real; pilot verifies **tenant_id** on every path. |

**Gap vs “routine intelligence”:** Ingestion **plumbing** can be “done” while **Cartographer extraction quality** and **coverage** for that tenant’s real volume still need validation (**Epic 6**).

---

### Phase 2 — Strategist loaders read the graph (digest / phase / evening — not fixtures-by-default)

| Intent | `epics.md` alignment | Built on `main`? | Pilot‑truth notes |
|--------|----------------------|------------------|-------------------|
| Morning digest, phase, evening from **materialized** reads | **Epic 8** — **8.1–8.3**; **Epic 16** — **16.4** (digest loader vertical slice), **16.1** (tenant context in shell) | **Done** in sprint-status | [`epic-8-implementation-status.md`](./epic-8-implementation-status.md): **not every Given/When/Then** in Epic **8** equals Oracle‑fed digest / NFR clocks. **`STRATEGIST_*_SOURCE_URL`** and fixtures remain valid **escape hatches**. |
| Evidence continuity | **Epic 8** — **8.4**; **Epic 16** — **16.5** (evidence deeplink tenant resolution) | **done** | Evidence IDs must exist in **canonical graph** for pilot — not only fixture-linked chips. |

**Primary stories:** **16.4**, **16.5**, plus ongoing Epic **8** hardening per [`epic-8-implementation-status.md`](./epic-8-implementation-status.md).

---

### Phase 3 — Meeting signal + in‑meeting slice from **trusted** calendar/presence

| Intent | `epics.md` alignment | Built on `main`? | Pilot‑truth notes |
|--------|----------------------|------------------|-------------------|
| Detection + ≤8s render path | **Epic 9** — **9.1** (FR36, NFR1) | **done** | Spec asks **real meeting detection** — sprint done means **UX + timing hooks** exist; **stub/env** paths documented in [`whats-actually-here.md`](../../whats-actually-here.md). |
| Meeting presence honesty | **Epic 15** — **15.4** (meeting‑presence pilot scope vs Graph) | **done** | Must explicitly choose **stub tenant** vs **Graph‑backed** for pilot; aligns with Epic List language. |

---

### Phase 4 — Oracle / Cartographer on **tenant** retrieval (novel ranked suggestions)

| Intent | `epics.md` alignment | Built on `main`? | Pilot‑truth notes |
|--------|----------------------|------------------|-------------------|
| Mission triage, extraction, phase‑gated retrieval, 3‑item budget, ranked‑out | **Epic 6** — **6.1–6.8** | **done** in sprint-status | Agents/contracts/evals exist; **browser loop** may still be **health URLs + mocks** per whats‑actually‑here — **wire Oracle outputs into digest/in‑meeting** for **one tenant** is typically **remaining integration**, not a green checkbox. |
| LLM + phase modulation | **Epic 5** — **5.4–5.6** | **done** | Tune **per pilot tenant**; correctness claims need **Epic 4** harness + tenant‑shaped fixtures. |

---

### Phase 5 — Queues durable + same IDs as digest/alerts

| Intent | `epics.md` alignment | Built on `main`? | Pilot‑truth notes |
|--------|----------------------|------------------|-------------------|
| Action / validation / solidification persistence | **Epic 9** — **9.4–9.7**; FR **56–59** | **done** (story grid) | [`whats-actually-here.md`](../../whats-actually-here.md): queues often **`strategist-queues-store`** **in‑memory BFF** — **Story 15.3** (CP‑backed queues **or** signed single‑replica ops contract) marked **done** in sprint-status **as scoped** — **verify** which branch the pilot runs under; multi‑replica still needs **CP/DB‑backed** queue APIs if FDE tests multiple web replicas (see **`whats-actually-here`** §10). |

---

### Phase 6 — “Novel & correct” governance (evaluation + ops)

| Intent | `epics.md` alignment | Built on `main`? | Pilot‑truth notes |
|--------|----------------------|------------------|-------------------|
| Replay parity, judges, 11th‑call gate | **Epic 4** — **4.3–4.8** | **done** | Runs in CI/harness — extend to **pilot tenant**-shaped corpora / redacted exports. |
| Degradation explicit | **Epic 6** — **6.8**; FR **46** | **done** | Confirm strategist UI shows **agent outage** vs silent staleness. |

---

## Consolidated view: one‑pilot tenant critical path

For **one pilot tenant**, **`epics.md` already sequences**:

1. **Epic 15** prerequisites (hosted session, durability stance, meeting‑presence honesty, runbooks).
2. **Epic 16** design‑partner path (onboarding, integrations UX, **CP-backed loaders**).

**Our phased plan maps cleanly:**

| Pilot phase | Dominant epics (this repo’s vocabulary) |
|-------------|-------------------------------------------|
| 0 | **15**, **16** (playbook / scope) |
| 1 | **3** + **1** |
| 2 | **16** + **8** (loader honesty) |
| 3 | **9** + **15** |
| 4 | **6** + **5** (+ **4** for proof) |
| 5 | **9** + **15** (durability) |
| 6 | **4** (+ compliance posture **12.x** if export/audit promised) |

---

## Explicit “built vs not built” summary

| Area | Sprint grid (`sprint-status`) | Pilot closed‑loop (`whats-actually-here`) |
|------|-------------------------------|-------------------------------------------|
| Monorepo, CI, schema, isolation | **Strong** | **Strong** |
| Ingestion services & CP direction | **Stories done** | **Partial** — verify real tenant throughput + non‑stub ASR/upload paths per deferred‑work |
| Strategist **UI** shell | **Strong** | **Strong** (demo‑capable) |
| **Same truth** digest ↔ alerts ↔ queues | Stories exist | **Often mock/BFF** until loaders + durable queues proven for pilot |
| **Oracle “routine novel intelligence”** | Contracts + Epics **5–6** closed | **Integration gap** — wire to **tenant graph** on schedule, not only harness |

---

## Suggested next BMAD actions

1. Add or refresh **one** **Epic 16**‑style story file that names **acceptance** as “pilot tenant **T** runs **without** `STRATEGIST_*` URLs for digest phase **X**” (measurable).
2. Mirror **queue durability** decision from Epic **15** into **`whats-actually-here`** §7 checklist when CP‑backed queues land.
3. Keep **`epic-8-implementation-status.md`** updated when digest is Oracle‑fed — it is the honesty brake for Epic **8** marketing language.

---

## References

- [`epics.md`](../planning-artifacts/epics.md) — Epic List §Epic 15–16, dependency §Epic 15 gates Epic 16  
- [`mvp-operating-plan-2026.md`](../planning-artifacts/mvp-operating-plan-2026.md) — sequencing note vs shipped `main`  
- [`development-board.yaml`](./development-board.yaml) — MVP tracks  

**Generated:** 2026-04-28 · aligns pilot phases discussed in implementation planning with existing epic/story numbering.
