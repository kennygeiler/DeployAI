# Agent Kenny — eval harness

The eval harness exercises Agent Kenny v2 against the BlueState-XL
fixture using 30 hand-curated golden questions
([scope-v2 §11.1](./scope-v2.md)) plus a **derived ground-truth set**
(171 questions generated from the XL seeder itself — ticket G2) and a
**longitudinal replay** that bounds retrieval quality across corpus
growth (ticket G3). Workflow:
`.github/workflows/agent-kenny-eval.yml` (scheduled + manual) plus the
deterministic PR gate job `agent-kenny-pr-gate` in
`.github/workflows/ci.yml`.

**Headline claim the harness now supports:** retrieval quality bounded
across a 5-year corpus; zero cross-engagement leaks enforced. The
longitudinal gate replays an identical question subset at 0.5y/2y/5y
corpus horizons and hard-fails if pass_rate degrades beyond tolerance or
any answer cites another engagement.

## What it covers

Per question: latency, tool calls, citation totals (verified /
unverified / `cross_engagement_leak`), revision attempts, adversarial
concerns, "I don't know" usage, and pass verdicts:

- `substring_pass` — case-insensitive substring match of every
  `expected_answer_contains` term.
- `judged_pass` — optional second-tier LLM judge (ticket G4). Enabled
  with `EVAL_LLM_JUDGE=1`; the judge runs only when the substring check
  FAILED on a factual question (pre-filter keeps LLM cost at zero for
  passing runs), uses the configured provider, and is skipped silently
  on the stub provider (`judged_pass: null`).
- `expected_pass` — the headline verdict: `substring_pass` OR
  `judged_pass == true`.

`hallucination_rate` is honest as of ticket G4: a factual (non-decline)
reply with **zero citations** counts as fully unverified — one phantom
unverified citation on both sides of the ratio — so a single uncited
factual answer scores 1.0 instead of a perfect 0.0. Declines, empty
replies, and the six `negative` questions (flagged
`is_negative_control: true` in `questions.yaml`) are exempt: a
citation-free decline is the correct outcome there.

## Derived ground truth (ticket G2)

The BlueState-XL generator is deterministic (uuid5 over stable labels),
so it knows every stakeholder, decision, risk, and edge it seeds. The
derivation CLI walks that knowledge (an additive introspection side
channel on `build_xl_scenario_sql` — the seed SQL is byte-identical with
or without it) and emits questions whose expected answers are **exact
seeded strings** and whose expected citations are **real seeded UUIDs**:

```bash
cd services/control-plane
uv run python -m tests.golden.agent_kenny.derive --out derived-questions.yaml
# derived 171 questions -> derived-questions.yaml
#   causal_chain: 40          sponsor_lookup: 40
#   dependency_lookup: 20     risk_status: 35
#   temporal: 12  negative_control: 12  cross_engagement: 12
```

Each derived question carries `template`, `difficulty`,
`expected_citation_ids` (seeded ledger-event/node/insight UUIDs — the
runner reports how many were actually cited via
`expected_citation_ids_matched/total`), and `valid_from_week` — the
earliest engagement week by which all its facts exist. Facts are chosen
to be **monotone** (e.g. "open" status only for risks that never close),
so a question valid at week N stays valid at every longer horizon.

Run any derived file through the runner with `--questions PATH`
(alternate files skip the curated-30 distribution check):

```bash
uv run python -m tests.golden.agent_kenny.runner \
  --questions derived-questions.yaml --limit 20 --report /tmp/derived-report.json
```

## Longitudinal replay + degradation contract (ticket G3)

The XL seeder gained an explicit progressive mode
(`apply_bluestate_xl_scenario(..., horizon_weeks=N)`): it seeds the
FIRST N weeks of the engagement as a true prefix of the full corpus —
same UUIDs, later events simply absent, risks not yet closed still open —
with the time anchor shifted so week N ends 21 quiet days before "now".
(This is distinct from `--seed-days`, which only trims snapshot
backfill.)

```bash
uv run python -m tests.golden.agent_kenny.longitudinal \
  --checkpoints 182,365,730,1095,1825 --questions derived \
  --per-checkpoint 12 --seed 0 --report /tmp/longitudinal.json
```

Per checkpoint the CLI drops + re-migrates the schema, reseeds the
horizon prefix, and replays **one fixed question subset** — sampled
deterministically from the questions valid at the earliest checkpoint —
recording pass_rate, citation precision (fraction of expected seeded
citation ids actually cited), latency p50/p95, and leak count. Holding
the subset fixed is what makes pass_rate comparable: same questions,
growing haystack.

The degradation contract:

- **exit 2** — any cross-engagement leak at any checkpoint. Security
  gate; treat as an incident (see below).
- **exit 3** — a checkpoint's pass_rate drops more than the tolerance
  (`--tolerance`, or env `DEGRADATION_TOLERANCE`, default **0.10**)
  below the best pass_rate of any *earlier (shorter-horizon)*
  checkpoint — a slow bleed across checkpoints trips it too.
- **exit 1** — transport/harness errors.

CI runs this weekly (`longitudinal` job in agent-kenny-eval.yml):
stub provider (deterministic, measures retrieval, zero API spend),
3 checkpoints (182/730/1825 days) for runtime sanity, report uploaded
as artifact `agent-kenny-longitudinal-<run_id>`.

## Persisting reports (ticket G3)

The golden runner can POST its report to the control plane after writing
it locally:

```bash
uv run python -m tests.golden.agent_kenny.runner \
  --report /tmp/eval-report.json \
  --persist-url https://cp.internal/internal/v1/admin/eval-runs \
  --persist-key "$DEPLOYAI_INTERNAL_API_KEY"
```

The report JSON is sent as the body with header
`X-DeployAI-Internal-Key`. Persistence is best-effort by contract: any
failure logs a warning and never changes the exit code (the receiving
endpoint `POST /internal/v1/admin/eval-runs` is being built in
parallel).

## CI cadence

| Trigger | Selection | When |
|---|---|---|
| `cron: 0 7 * * *` | 5 random questions (seeded by `GITHUB_RUN_ID`) | Nightly 07:00 UTC |
| `cron: 0 8 * * 1` | All 30 | Mondays 08:00 UTC |
| `cron: 0 8 * * 1` (`longitudinal` job) | Longitudinal replay: derived questions, checkpoints 182/730/1825d, stub provider, degradation + leak gates | Mondays 08:00 UTC |
| `workflow_dispatch` | CSV of question IDs (empty = all 30); also runs the longitudinal job | On demand |
| `pull_request` (ci.yml `agent-kenny-pr-gate`) | Fixed subset `q-017,q-018,q-019,q-023,q-024`, stub provider | Every PR touching `services/control-plane/**` |

The scheduled workflow invokes the runner CLI directly (no pytest). The
nightly random sample is reproducible: rerun locally with
`--seed <run_id>`.

The PR gate is deterministic by construction — negative +
cross-engagement questions, stub LLM (no API key), fresh pgvector
testcontainer — and blocks the PR unless `pass_rate == 1` and
`cross_engagement_leak_count == 0`.

Secrets (optional, scheduled workflow):

- `AGENT_KENNY_EVAL_ANTHROPIC_API_KEY` — real-LLM runs. Absent → stub
  provider: the run still completes and the leak gate still executes,
  but factual questions honestly report `pass_rate` 0.
- `AGENT_KENNY_EVAL_SLACK_WEBHOOK_URL` — failure alert webhook.

## Where to find the report

Every run uploads `eval-report.json` as artifact
`agent-kenny-eval-<run_id>` with 90-day retention. Pull via:

```bash
gh run download <run_id> -n agent-kenny-eval-<run_id>
```

## Running locally

The CLI owns the whole harness: with no `DATABASE_URL` in the
environment it starts the same `pgvector/pgvector:pg16` testcontainer
the integration conftest uses, bootstraps extensions, runs alembic,
seeds BlueState-XL, and drives the FastAPI app in-process over
`ASGITransport`. Docker is the only requirement.

```bash
cd services/control-plane
uv sync
uv run python -m tests.golden.agent_kenny.runner --limit 5 --random --seed 7
```

Flags:

| Flag | Meaning |
|---|---|
| `--limit N` | run only N questions |
| `--random` | sample the subset randomly (seeded) instead of YAML order |
| `--seed S` | RNG seed for `--random`; defaults to `GITHUB_RUN_ID` in CI, else 0 |
| `--question-ids a,b` | explicit subset (e.g. `q-007,q-023`); mutually exclusive with `--limit/--random` |
| `--report PATH` | report location (default `eval-reports/agent-kenny-<ts>.json`) |
| `--runtime legacy\|langgraph` | exported as `DEPLOYAI_AGENT_RUNTIME` (ticket D2 flag; `langgraph` takes effect once the D2 runtime lands) |
| `--seed-days D` | BlueState-XL snapshot backfill horizon (default 30 for speed; production fixture uses 1825) |
| `--questions PATH` | alternate questions YAML (e.g. the G2 derived set); skips the curated-30 distribution check |
| `--persist-url URL` / `--persist-key KEY` | best-effort POST of the report to `POST /internal/v1/admin/eval-runs` (warns on failure, never fails the run) |

Environment:

- `DATABASE_URL` — reuse an existing Postgres (must accept
  `CREATE EXTENSION vector`); the CLI migrates + seeds it in place.
  Unset → throwaway testcontainer.
- `ANTHROPIC_API_KEY` / `DEPLOYAI_LLM_PROVIDER` — LLM selection, same
  resolution as the app. No key → stub provider (offline, deterministic).
- `EVAL_LLM_JUDGE=1` — enable the second-tier judge.

Exit codes: `0` clean run, `1` at least one transport/harness error,
`2` cross-engagement leak detected.

Reproduce the PR gate exactly:

```bash
DEPLOYAI_LLM_PROVIDER=stub uv run python -m tests.golden.agent_kenny.runner \
  --question-ids q-017,q-018,q-019,q-023,q-024 --seed 0 --report /tmp/eval-report-pr.json
```

## Interpreting `cross_engagement_leak` failures

A non-zero `cross_engagement_leak_count` **fails the job** — the gate
step in the workflow runs unconditionally (ticket G5) and the CLI also
exits 2. Per [scope-v2 §7.1](./scope-v2.md), a cross-engagement
citation is always a tenant-isolation regression and must never reach a
user. Treat any leak as a security incident:

1. Download the report; identify failing question IDs.
2. Reproduce locally with `--question-ids <id>`; confirm the cited row
   resolves into another engagement.
3. Patch the offending tool's scoping (regressions are almost always
   in a tool, not in LLM output) and pin the fix with a unit test.
4. **Do not re-run the eval to "see if it passes" before patching.**
   Re-runs do not clear the incident; the audit trail expects fix
   then verify.

Adversarial-concern flags are watched but do not fail the build —
Wave C's dashboard surfaces those trends. `hallucination_rate` is
reported (honestly — see above) but not yet a hard gate.
