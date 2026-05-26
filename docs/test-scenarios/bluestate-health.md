# Test scenario: BlueState Health — Member Portal Replatform

End-to-end deterministic corpus for exercising every Phase F analyzer
against a 26-week engagement. Built by
[`seed_scenario_bluestate.py`][seed-script] from the [event
catalogue][events-data]; reuses the tenant + users from
[`seed_app.py`][seed-app] (one team can own multiple engagements).

[seed-script]: ../../infra/compose/seed/seed_scenario_bluestate.py
[events-data]: ../../infra/compose/seed/scenario_data/bluestate_events.py
[seed-app]: ../../infra/compose/seed/seed_app.py

## Usage

```bash
make compose-up                  # if not already up
make seed-scenario-bluestate     # idempotent re-runnable seed
```

The seed:

1. Reuses the existing tenant (`11111111-…`) + 3 deployment-team users.
2. Creates one engagement at `dddddddd-dddd-4ddd-8ddd-dddddddddddd`
   ("BlueState Health — Member Portal Replatform").
3. Emits the full 26-week ledger via direct SQL inserts (anchored so W26
   ends ~21 days before wall-clock `now`, leaving a trailing silent
   window for `engagement_silence`).
4. Backfills 182 daily `matrix_snapshots`.
5. Runs `control_plane.intelligence.scheduler.run_analyzers` at six
   scenario-time anchors so every analyzer's default window catches the
   right event cluster (see §Analyzer run schedule below).

## Engagement summary

| Field            | Value                                                |
| ---------------- | ---------------------------------------------------- |
| Engagement ID    | `dddddddd-dddd-4ddd-8ddd-dddddddddddd`               |
| Tenant ID        | `11111111-1111-1111-1111-111111111111`               |
| Customer         | BlueState Health (regional payer, ~2M members)       |
| Scope            | Member portal replatform — identity, eligibility, claims viewer, find-a-doctor, in-portal messaging |
| Duration         | 26 weeks (W26 ends ~21 days before `now`)            |
| DeployAI team    | Sarah Chen (lead), Marcus Rivera (FDE), Jamie Park (biz dev) |

## Phase timeline

| Window | Focus | Key signals |
|---|---|---|
| W1–4 Discovery   | Kickoff, integration inventory, MSA, 4 decisions ratified, ~95% acceptance | Patricia / Tom / Lisa / Raj / Maya onboarded |
| W5–12 Design     | 6 decisions, 3 risks opened, 2 closed, ~3d cycle, ~90% acceptance | Eligibility cache, claims viewer, pilot cohort, pen-test vendor |
| W13–16 Build     | 4 decisions, cycle creeping to ~7d, **stakeholder churn in W14** | Tom departs, Lisa rotates off, Sandra + David + Priya + Carla onboard |
| W17–19 SILENCE   | 0 events (planned contractor handoff + holiday) | `engagement_silence` window |
| W20–24 Pilot prep | 3 decisions accepted + 6 rejected, **8 risks opened in W22**, decision cycle = 3d, +8 extractor-noise auto-proposals (W20-21) | Pen-test, identity remediation, PHI scope opt-in, DR drill, GO/no-go |
| W25–26 Pre-launch | 2 decisions, 3 risks closed | Pen-test retest clean, comms cadence, GO decision |

## Expected ledger totals

After `make seed-scenario-bluestate` you should see (queryable via
the smoke psql blocks at the bottom of this doc):

| `ledger_events.source_kind` | Count |
| --- | --- |
| `email_ingest`         | 58 |
| `llm_proposal_created` | 34 (20 decision + 8 extractor-noise + 6 rejected) |
| `proposal_accepted`    | 28 (16 decision + 8 extractor-noise + 4 extra W22-26 decisions) |
| `meeting_webhook`      | 23 |
| `matrix_node_created`  | 20 (10 stakeholder adds + 6 system + 4 commitment) |
| `manual_capture`       | 14 |
| `insight_opened`       | 13 (risks) |
| `proposal_rejected`    | 6  (concentrated W23–24) |
| `insight_closed`       | 5  (risks closed) |
| `member_added`         | 3  (Sarah / Marcus / Jamie) |
| `matrix_node_deleted`  | 3  (Tom / Lisa / Maya departures in W14) |
| **Total**              | **207** |

`matrix_nodes` by node_type at end:

| node_type | count |
| --- | --- |
| `decision`    | 20 |
| `stakeholder` |  7 (10 added – 3 deleted) |
| `system`      |  6 |
| `commitment`  |  4 |

`matrix_snapshots`: **182** (one per UTC day for 26 weeks).

`ledger_event_causes`: **93** edges. Every `proposal_accepted` carries
the `llm_proposal_created` parent plus up to 3 narrative
parents (emails / meetings / captures) from the same week, so the
provenance analyzer has a chain to walk.

## Analyzer run schedule

The `/internal/v1/intelligence/run` HTTP endpoint uses `datetime.now(UTC)`
and from a single invocation can only catch one or two analyzers against
a 26-week corpus (silence and risk-burst windows are mutually exclusive
under a single `now`). The seed calls `run_analyzers` programmatically
at six scenario-time anchors so each analyzer's default window hits the
expected signal:

| Anchor `now` | Fires |
| --- | --- |
| end of W14            | `stakeholder_churn` (3 departures vs 0 prior 30d) |
| end of W16 + 1d       | `decision_cycle_slowdown` (W13–16 build cycle vs W11–14 design) |
| end of W22 + 1d       | `risk_open_rate` (8 new risks in 14d, threshold 5) |
| end of W24 + 2d       | `extractor_acceptance_drift` (W23–24 rejections drop the 14d rate by 37pp) |
| W26 GO accept + 12h   | `decision_provenance_summary` (24h window catches the GO accept; chain has 4 parents) |
| wall-clock `now`      | `engagement_silence` (trailing 21d empty) |

## Expected `temporal_insights` rows

| insight_kind                  | severity | Title paraphrase                          | Evidence |
| --- | --- | --- | --- |
| `stakeholder_churn`           | medium   | "Stakeholder churn doubled (0 → 3)"     | 3× `matrix_node_deleted` (stakeholder) in W14 |
| `decision_cycle_slowdown`     | low      | "Decision cycle slowed ~88%"              | W13–16 decisions paired (~7d cycle) vs W11–14 prior (~3d) |
| `risk_open_rate`              | low      | "Net risk count rose by 8"                | 8× `insight_opened`(risk) in W22, 0 closed |
| `extractor_acceptance_drift`  | medium   | "Extractor acceptance dropped 37pp"       | 14d ending W24+2d has 4–5 extractor proposals @ ~0% accept vs 30d baseline ~37% |
| `decision_provenance_summary` | info     | "Provenance: …Go/no-go: GO for pilot launch" | Walks the W26 GO accept up through `llm_proposal_created` + W26 narrative events; LLM-rendered narrative |
| `engagement_silence`          | info     | "No activity in 14 days"                  | No ledger events in the 14d window ending wall-clock `now` |

A second `stakeholder_churn` row is expected — the analyzer fires for
both the W14-end and W16+1d runs because both windows still contain the
3 W14 deletions in their current 30d slice. The deterministic ID is keyed
on `(kind, engagement_id, window_start, window_end)` so they upsert
distinctly.

## Smoke output (verbatim from a successful run)

This was produced on 2026-05-26 against the compose stack with the
upgraded control-plane image:

```
=== ledger_events by source_kind ===
     source_kind      | count
----------------------+-------
 email_ingest         |    58
 llm_proposal_created |    34
 proposal_accepted    |    28
 meeting_webhook      |    23
 matrix_node_created  |    20
 manual_capture       |    14
 insight_opened       |    13
 proposal_rejected    |     6
 insight_closed       |     5
 member_added         |     3
 matrix_node_deleted  |     3
(11 rows)

=== matrix_nodes by node_type ===
  node_type  | count
-------------+-------
 decision    |    20
 stakeholder |     7
 system      |     6
 commitment  |     4
(4 rows)

=== matrix_snapshots ===
 count
-------
   182

=== ledger_event_causes ===
 count
-------
    93

=== temporal_insights ===
        insight_kind         | severity |                                  title
-----------------------------+----------+-------------------------------------------------------------------------
 decision_provenance_summary | info     | Provenance: proposal accepted: decision — Go/no-go: GO for pilot launch
 engagement_silence          | info     | No activity in 14 days
 extractor_acceptance_drift  | medium   | Extractor acceptance dropped 37pp
 risk_open_rate              | low      | Net risk count rose by 8
 stakeholder_churn           | medium   | Stakeholder churn doubled (0 → 3)
 stakeholder_churn           | medium   | Stakeholder churn doubled (0 → 3)
(6 rows)
```

All six analyzer `insight_kind` values are present, matching the contract
in the brief's "Required acceptance" section.

## Smoke verification commands

```bash
# Source-kind totals
docker compose -f infra/compose/docker-compose.yml exec postgres psql -U deployai -d deployai -c \
  "SELECT source_kind, count(*) FROM ledger_events WHERE engagement_id='dddddddd-dddd-4ddd-8ddd-dddddddddddd' GROUP BY 1 ORDER BY 2 DESC;"

# Node-type totals
docker compose -f infra/compose/docker-compose.yml exec postgres psql -U deployai -d deployai -c \
  "SELECT node_type, count(*) FROM matrix_nodes WHERE engagement_id='dddddddd-dddd-4ddd-8ddd-dddddddddddd' GROUP BY 1;"

# Snapshot count (expect 182)
docker compose -f infra/compose/docker-compose.yml exec postgres psql -U deployai -d deployai -c \
  "SELECT count(*) FROM matrix_snapshots WHERE engagement_id='dddddddd-dddd-4ddd-8ddd-dddddddddddd';"

# Causal-chain edge total
docker compose -f infra/compose/docker-compose.yml exec postgres psql -U deployai -d deployai -c \
  "SELECT count(*) FROM ledger_event_causes c JOIN ledger_events e ON c.event_id=e.id WHERE e.engagement_id='dddddddd-dddd-4ddd-8ddd-dddddddddddd';"

# Analyzer-produced insights (expect all 6 insight_kinds)
docker compose -f infra/compose/docker-compose.yml exec postgres psql -U deployai -d deployai -c \
  "SELECT insight_kind, severity, title FROM temporal_insights WHERE engagement_id='dddddddd-dddd-4ddd-8ddd-dddddddddddd' ORDER BY insight_kind, window_end;"
```

If the temporal-insight result set is missing a kind, **fix the scenario
data, not the analyzer** — adjust the relevant cluster in
[`bluestate_events.py`][events-data] (e.g., add a risk in W22, widen the
churn cluster, or extend the proposal-cycle creep) and re-run
`make seed-scenario-bluestate`.

## Realism boundaries (documented deviations from analyzer brief)

A few deliberate compromises were made so a single seed run can fire all
six analyzers on the same corpus:

- **W14 stakeholder churn is 3 departures, not the brief's "Tom departs
  + 2 adds"**: the `stakeholder_churn` analyzer only counts
  `matrix_node_deleted` (departures); additions are tracked elsewhere.
  So Lisa Wong is rotated off the program and Maya Singh hands procurement
  to her deputy in the same window. Two new VPs (Sandra Kim, David Liu)
  plus two deputies (Priya Subramanian, Carla Diaz) are still added on
  top.
- **W20+ decision cycle is 3 days, not 8**: the analyzer pairs
  `llm_proposal_created` and `proposal_accepted` within the SAME window;
  an 8-day cycle pushes the accept past the 14d window for
  `extractor_acceptance_drift`. The narrative copy in the seed still
  describes a "stretched" cycle for realism but the event timestamps
  use a 3-day cycle.
- **8 extractor-noise auto-proposals in W20–21**: these are non-decision
  `llm_proposal_created` + `proposal_accepted` pairs that bulk up the
  30d trailing baseline for `extractor_acceptance_drift` ahead of the
  W23–24 reject cluster. They represent the matrix extractor surfacing
  smaller system/stakeholder/edge proposals automatically — a realistic
  background-noise signal.
- **W26 ends ~21 days before wall-clock `now`, not exactly today**:
  ensures the trailing 14d window for `engagement_silence` is reliably
  empty even if the seed run lands on a slightly stale clock.
