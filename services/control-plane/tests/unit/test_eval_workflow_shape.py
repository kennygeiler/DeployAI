"""Shape-check the Phase 6 Wave B eval workflow.

The workflow itself is exercised by GitHub on a schedule; this unit
test enforces the contract callers (Wave A's runner, Wave C's
dashboard) depend on:

* both cron schedules present (nightly 5Q + weekly 30Q),
* manual `workflow_dispatch` with a `question_ids` input,
* the `cross_engagement_leak_count` hard-fail gate is wired into the
  eval job, and
* the eval-report artifact is uploaded with the expected name + 90 day
  retention.

If any of these are silently removed in a future refactor the smoke
test fails before the workflow misses its next 07:00 UTC run.
"""

from __future__ import annotations

from pathlib import Path

import yaml

WORKFLOW_PATH = (
    Path(__file__).resolve().parents[4] / ".github" / "workflows" / "agent-kenny-eval.yml"
)


def _load_workflow() -> dict:
    assert WORKFLOW_PATH.exists(), f"missing workflow file: {WORKFLOW_PATH}"
    return yaml.safe_load(WORKFLOW_PATH.read_text())


def test_workflow_file_loads() -> None:
    wf = _load_workflow()
    assert wf["name"] == "Agent Kenny eval"


def test_both_cron_schedules_present() -> None:
    wf = _load_workflow()
    # PyYAML maps the bare ``on:`` key to True on safe_load. Tolerate
    # either spelling so a future quoting change doesn't break the test.
    triggers = wf.get("on") or wf.get(True)
    assert triggers is not None, "workflow has no triggers"

    schedules = triggers.get("schedule") or []
    crons = {entry["cron"] for entry in schedules}
    assert "0 7 * * *" in crons, "nightly 5Q cron (07:00 UTC) missing"
    assert "0 8 * * 1" in crons, "weekly 30Q cron (Monday 08:00 UTC) missing"


def test_workflow_dispatch_accepts_question_ids() -> None:
    wf = _load_workflow()
    triggers = wf.get("on") or wf.get(True)
    dispatch = triggers.get("workflow_dispatch")
    assert dispatch is not None, "workflow_dispatch trigger missing"
    inputs = dispatch.get("inputs") or {}
    assert "question_ids" in inputs, "workflow_dispatch is missing the question_ids input"


def test_eval_job_has_cross_engagement_gate() -> None:
    wf = _load_workflow()
    job = wf["jobs"]["eval"]
    step_names = [step.get("name", "") for step in job["steps"]]
    gate_steps = [name for name in step_names if "Cross-engagement" in name]
    assert gate_steps, (
        "eval job is missing the cross-engagement-leak gate step "
        "(expected a step whose name contains 'Cross-engagement')"
    )

    gate = next(
        step for step in job["steps"] if "Cross-engagement" in step.get("name", "")
    )
    run_script = gate.get("run", "")
    assert "cross_engagement_leak_count" in run_script, (
        "gate step does not reference cross_engagement_leak_count"
    )
    assert "exit 1" in run_script, "gate step does not exit non-zero on leak"


def test_artifact_upload_is_configured() -> None:
    wf = _load_workflow()
    job = wf["jobs"]["eval"]
    upload_steps = [
        step
        for step in job["steps"]
        if isinstance(step.get("uses"), str)
        and step["uses"].startswith("actions/upload-artifact@")
    ]
    assert upload_steps, "eval job has no upload-artifact step"
    upload = upload_steps[0]
    with_block = upload.get("with") or {}
    assert with_block.get("name", "").startswith("agent-kenny-eval-"), (
        "artifact name must be prefixed agent-kenny-eval-"
    )
    assert int(with_block.get("retention-days", 0)) == 90, (
        "artifact retention must be 90 days"
    )


def test_permissions_are_least_privilege() -> None:
    wf = _load_workflow()
    perms = wf.get("permissions") or {}
    assert perms.get("contents") == "read", (
        "workflow-level permissions must be contents: read (no write scopes)"
    )
