# Golden query fixtures (Epic 4, Stories 4-3/4-4, NFR50/NFR53)

## Layout

- `tests/golden/queries/*.yaml` — one file per query; fields validated by `pnpm run golden:validate`.
- **Phases (7):** `discovery` · `planning` · `integration` · `pilot` · `scale` · `steady_state` · `sunset` (DeployAI 7-phase framework).
- **Topologies (3):** `single_stakeholder` · `cross_agency` · `multi_jurisdictional` (21-cell phase-retrieval audit matrix = 7×3).

## Schema (per query)

| Field | Required | Notes |
|--------|-----------|--------|
| `query_id` | yes | Unique string, stable across releases. |
| `phase` | yes | One of the 7 phases. |
| `stakeholder_topology` | yes | One of 3. |
| `query_text` | yes | Natural-language query under test. |
| `tenant_scenario` | no | e.g. `default`, `federal`, … (5 scenarios in 4-4). |
| `judge_only` | no | `true` → no deterministically expected node IDs; evaluated by LLM-judge (4-6) only. If false/missing, `expected_citations` must be non-empty. |
| `expected_citations` | conditional | List of `{ node_id, must_appear, rank_floor }` (see epics 4-3/4-4). Empty allowed only with `judge_only: true`. |

## Authoring

```bash
pnpm run golden:author -- --id my-query-001 --phase discovery --topo single_stakeholder
```

Edits the placeholder and expected citation UUIDs. SME-authored queries should replace synthetic `gen-*` text over time (see [golden-corpus-derivation.md](./golden-corpus-derivation.md)).

## Bulk / CI harness

- `pnpm run golden:expand-corpus` — regenerates `gen-0001` … (default 200) for pipeline coverage; **overwrites** previous `gen-*.yaml` only.
- `pnpm run golden:validate` — fails CI if the 21 matrix cells are not represented or the schema is wrong.

## Relationship to `expected/*.json`

Optional per-query JSON expectations can live in `tests/golden/expected/` in later story refinements; v1 embeds `expected_citations` inline in YAML.
