# Agent Kenny — eval harness

The eval harness exercises Agent Kenny v2 against the BlueState-XL
fixture using 30 hand-curated golden questions
([scope-v2 §11.1](./scope-v2.md)). Workflow:
`.github/workflows/agent-kenny-eval.yml`.

## What it covers

Per question: latency, tool calls, citation totals (verified /
unverified / `cross_engagement_leak`), revision attempts, adversarial
concerns, "I don't know" usage, and a semantic-match score against
the expected answer.

## CI cadence

| Trigger | Selection | When |
|---|---|---|
| `cron: 0 7 * * *` | 5 random questions | Nightly 07:00 UTC |
| `cron: 0 8 * * 1` | All 30 | Mondays 08:00 UTC |
| `workflow_dispatch` | CSV of question IDs (empty = all 30) | On demand |

## Where to find the report

Every run uploads `eval-report.json` as artifact
`agent-kenny-eval-<run_id>` with 90-day retention. Pull via:

```bash
gh run download <run_id> -n agent-kenny-eval-<run_id>
```

## Running locally

```bash
cd services/control-plane
uv sync
uv run alembic upgrade head
uv run python -m control_plane.scenarios.bluestate_xl.runner
uv run python -m tests.golden.agent_kenny.runner --limit 5 --random
```

For a specific subset: `--question-ids q07,q23`.

## Interpreting `cross_engagement_leak` failures

A non-zero `cross_engagement_leak_count` **fails the job**. Per
[scope-v2 §7.1](./scope-v2.md), a cross-engagement citation is always
a tenant-isolation regression and must never reach a user. Treat any
leak as a security incident:

1. Download the report; identify failing question IDs.
2. Reproduce locally with `--question-ids <id>`; confirm the cited row
   resolves into another engagement.
3. Patch the offending tool's scoping (regressions are almost always
   in a tool, not in LLM output) and pin the fix with a unit test.
4. **Do not re-run the eval to "see if it passes" before patching.**
   Re-runs do not clear the incident; the audit trail expects fix
   then verify.

Hallucination (`not_found`) and adversarial-concern flags are watched
but do not fail the build — Wave C's dashboard surfaces those trends.
