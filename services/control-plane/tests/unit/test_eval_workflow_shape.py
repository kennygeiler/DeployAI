"""Shape-check the Agent Kenny eval CI wiring (tickets G1/G5).

The workflows are exercised by GitHub on schedule / PR; these unit tests
enforce the contract the eval harness depends on:

* both cron schedules present (nightly 5Q + weekly 30Q),
* manual `workflow_dispatch` with a `question_ids` input,
* the eval step invokes the runner CLI directly (`python -m
  tests.golden.agent_kenny.runner`) — never pytest (the old pytest
  invocation exited 4 on every scheduled run and the leak gate never
  executed),
* the `cross_engagement_leak_count` hard-fail gate runs unconditionally
  (no `eval_skipped` soft-skip guard),
* the eval-report artifact is uploaded with the expected name + 90 day
  retention, and
* ci.yml carries the deterministic PR-gate job (stub provider, fixed
  question subset) keyed off the control_plane path filter.

If any of these are silently removed in a future refactor the smoke
test fails before the workflow misses its next 07:00 UTC run.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import yaml

_WORKFLOWS_DIR = Path(__file__).resolve().parents[4] / ".github" / "workflows"
WORKFLOW_PATH = _WORKFLOWS_DIR / "agent-kenny-eval.yml"
CI_WORKFLOW_PATH = _WORKFLOWS_DIR / "ci.yml"


def _load_workflow() -> dict[Any, Any]:
    assert WORKFLOW_PATH.exists(), f"missing workflow file: {WORKFLOW_PATH}"
    return cast("dict[Any, Any]", yaml.safe_load(WORKFLOW_PATH.read_text()))


def _load_ci_workflow() -> dict[Any, Any]:
    assert CI_WORKFLOW_PATH.exists(), f"missing workflow file: {CI_WORKFLOW_PATH}"
    return cast("dict[Any, Any]", yaml.safe_load(CI_WORKFLOW_PATH.read_text()))


def _triggers(wf: dict[Any, Any]) -> dict[Any, Any]:
    # PyYAML maps the bare ``on:`` key to True on safe_load. Tolerate
    # either spelling so a future quoting change doesn't break the test.
    triggers = wf.get("on") or wf.get(True)
    assert triggers is not None, "workflow has no triggers"
    return cast("dict[Any, Any]", triggers)


def test_workflow_file_loads() -> None:
    wf = _load_workflow()
    assert wf["name"] == "Agent Kenny eval"


def test_both_cron_schedules_present() -> None:
    schedules = _triggers(_load_workflow()).get("schedule") or []
    crons = {entry["cron"] for entry in schedules}
    assert "0 7 * * *" in crons, "nightly 5Q cron (07:00 UTC) missing"
    assert "0 8 * * 1" in crons, "weekly 30Q cron (Monday 08:00 UTC) missing"


def test_workflow_dispatch_accepts_question_ids() -> None:
    dispatch = _triggers(_load_workflow()).get("workflow_dispatch")
    assert dispatch is not None, "workflow_dispatch trigger missing"
    inputs = dispatch.get("inputs") or {}
    assert "question_ids" in inputs, "workflow_dispatch is missing the question_ids input"


def test_eval_step_invokes_runner_cli_not_pytest() -> None:
    """Ticket G1 — the eval must be a direct CLI invocation.

    The pre-G1 workflow ran ``pytest tests/golden/agent_kenny/ -m eval``
    against a directory with zero test functions and unregistered
    markers/options — pytest exited 4 (usage error) on every scheduled
    run. Lock the CLI invocation so that regression cannot return.
    """
    wf = _load_workflow()
    job = wf["jobs"]["eval"]
    run_scripts = [step.get("run", "") for step in job["steps"]]
    cli_steps = [s for s in run_scripts if "python -m tests.golden.agent_kenny.runner" in s]
    assert cli_steps, "eval job does not invoke the runner CLI (python -m tests.golden.agent_kenny.runner)"
    assert not any("pytest" in s for s in run_scripts), (
        "eval job must not invoke pytest — the golden dir has no test functions "
        "and the CLI is the supported entry point (ticket G1)"
    )


def test_eval_job_has_unconditional_cross_engagement_gate() -> None:
    """Ticket G5 — the leak gate runs even when the eval step failed."""
    wf = _load_workflow()
    job = wf["jobs"]["eval"]
    gates = [step for step in job["steps"] if "Cross-engagement" in step.get("name", "")]
    assert gates, (
        "eval job is missing the cross-engagement-leak gate step "
        "(expected a step whose name contains 'Cross-engagement')"
    )
    gate = gates[0]

    condition = str(gate.get("if", ""))
    assert "always()" in condition, "gate step must run unconditionally (if: always())"
    assert "eval_skipped" not in condition, (
        "gate step must not be guarded on eval_skipped — that guard meant the gate never executed (ticket G5)"
    )

    run_script = gate.get("run", "")
    assert "cross_engagement_leak_count" in run_script, "gate step does not reference cross_engagement_leak_count"
    assert "exit 1" in run_script, "gate step does not exit non-zero on leak"


def test_no_eval_skipped_soft_skip_anywhere() -> None:
    """The exit-5 soft-skip is dead; no step may reintroduce it."""
    wf = _load_workflow()
    for job in wf["jobs"].values():
        for step in job.get("steps", []):
            for field in ("if", "run"):
                assert "eval_skipped" not in str(step.get(field, "")), (
                    f"eval_skipped soft-skip must not reappear (step {step.get('name', '?')!r}, field {field})"
                )


def test_artifact_upload_is_configured() -> None:
    wf = _load_workflow()
    job = wf["jobs"]["eval"]
    upload_steps = [
        step
        for step in job["steps"]
        if isinstance(step.get("uses"), str) and step["uses"].startswith("actions/upload-artifact@")
    ]
    assert upload_steps, "eval job has no upload-artifact step"
    upload = upload_steps[0]
    with_block = upload.get("with") or {}
    assert with_block.get("name", "").startswith("agent-kenny-eval-"), (
        "artifact name must be prefixed agent-kenny-eval-"
    )
    assert int(with_block.get("retention-days", 0)) == 90, "artifact retention must be 90 days"


def test_permissions_are_least_privilege() -> None:
    wf = _load_workflow()
    perms = wf.get("permissions") or {}
    assert perms.get("contents") == "read", "workflow-level permissions must be contents: read (no write scopes)"


# --- ci.yml PR gate (ticket G5) -----------------------------------------------


def test_ci_has_deterministic_pr_gate_job() -> None:
    ci = _load_ci_workflow()
    job = ci["jobs"].get("agent-kenny-pr-gate")
    assert job is not None, "ci.yml is missing the agent-kenny-pr-gate job"
    assert "needs.changes.outputs.control_plane" in str(job.get("if", "")), (
        "PR gate must be keyed off the control_plane path filter"
    )

    run_scripts = [step.get("run", "") for step in job.get("steps", [])]
    gate_script = next((s for s in run_scripts if "tests.golden.agent_kenny.runner" in s), None)
    assert gate_script is not None, "PR gate does not invoke the runner CLI"
    assert "--question-ids" in gate_script, "PR gate must run a fixed --question-ids subset (deterministic)"
    assert "cross_engagement_leak_count" in gate_script, "PR gate must check cross_engagement_leak_count"

    env_blocks = [step.get("env") or {} for step in job.get("steps", [])]
    assert any(e.get("DEPLOYAI_LLM_PROVIDER") == "stub" for e in env_blocks), (
        "PR gate must force the stub provider (no LLM key on PRs)"
    )


def test_ci_changes_job_exposes_control_plane_filter() -> None:
    ci = _load_ci_workflow()
    changes = ci["jobs"]["changes"]
    assert "control_plane" in (changes.get("outputs") or {}), (
        "changes job must expose a control_plane output for the PR gate"
    )
