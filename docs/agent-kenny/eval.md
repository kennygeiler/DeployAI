# Agent Kenny — eval harness

The eval harness exercises Agent Kenny v2 against the BlueState-XL
fixture using 30 hand-curated golden questions
([scope-v2 §11.1](./scope-v2.md)). Workflow:
`.github/workflows/agent-kenny-eval.yml` (scheduled + manual) plus the
deterministic PR gate job `agent-kenny-pr-gate` in
`.github/workflows/ci.yml`.

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

## CI cadence

| Trigger | Selection | When |
|---|---|---|
| `cron: 0 7 * * *` | 5 random questions (seeded by `GITHUB_RUN_ID`) | Nightly 07:00 UTC |
| `cron: 0 8 * * 1` | All 30 | Mondays 08:00 UTC |
| `workflow_dispatch` | CSV of question IDs (empty = all 30) | On demand |
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
