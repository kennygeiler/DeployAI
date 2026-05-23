"""Smoke tests for `init.py` arg-parsing + required-value enforcement.

Side-effecting steps (psql, HTTP) are exercised manually against a live
compose stack — this file only covers the layer that decides what gets
run, not the steps themselves.

Run with:  python3 -m pytest infra/compose/seed/test_init.py
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import init as init_mod  # noqa: E402  — sys.path mutation above is intentional


@pytest.fixture
def mock_steps(monkeypatch: pytest.MonkeyPatch) -> dict[str, list[tuple]]:
    """Replace each side-effecting step with a recording stub."""
    calls: dict[str, list[tuple]] = {
        "tenant": [],
        "llm": [],
        "engagement": [],
        "user": [],
        "member": [],
    }
    monkeypatch.setattr(init_mod, "step_tenant", lambda *a: calls["tenant"].append(a))
    monkeypatch.setattr(init_mod, "step_llm_config", lambda *a: calls["llm"].append(a))
    monkeypatch.setattr(
        init_mod,
        "step_engagement",
        lambda *a: (calls["engagement"].append(a), "eng-uuid-stub")[1],
    )
    monkeypatch.setattr(
        init_mod,
        "step_user",
        lambda *a: (calls["user"].append(a), "user-uuid-stub")[1],
    )
    monkeypatch.setattr(init_mod, "step_member", lambda *a: calls["member"].append(a))
    return calls


def test_required_tenant_name_missing_exits(monkeypatch: pytest.MonkeyPatch) -> None:
    # Strip env so DEPLOYAI_INIT_* defaults can't satisfy the required check.
    for k in list(init_mod.ENV.keys()):
        if k.startswith("DEPLOYAI_INIT_"):
            monkeypatch.delitem(init_mod.ENV, k)
    monkeypatch.delenv("DEPLOYAI_INIT_TENANT_NAME", raising=False)
    with pytest.raises(SystemExit) as exc:
        init_mod.main(
            [
                "--llm-provider",
                "stub",
                "--engagement-name",
                "x",
                "--user-name",
                "kenny",
            ]
        )
    assert "tenant-name" in str(exc.value)


def test_required_llm_provider_missing_exits(monkeypatch: pytest.MonkeyPatch) -> None:
    for k in list(init_mod.ENV.keys()):
        if k.startswith("DEPLOYAI_") or k == "ANTHROPIC_API_KEY":
            monkeypatch.delitem(init_mod.ENV, k)
    monkeypatch.delenv("DEPLOYAI_LLM_PROVIDER", raising=False)
    monkeypatch.delenv("DEPLOYAI_INIT_LLM_PROVIDER", raising=False)
    with pytest.raises(SystemExit) as exc:
        init_mod.main(
            [
                "--tenant-name",
                "Acme",
                "--engagement-name",
                "x",
                "--user-name",
                "kenny",
            ]
        )
    assert "llm-provider" in str(exc.value)


def test_happy_path_runs_all_five_steps(
    mock_steps: dict[str, list[tuple]], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("DEPLOYAI_INIT_TENANT_ID", raising=False)
    rc = init_mod.main(
        [
            "--tenant-name",
            "Acme",
            "--llm-provider",
            "stub",
            "--engagement-name",
            "Pilot",
            "--user-name",
            "kenny",
        ]
    )
    assert rc == 0
    assert len(mock_steps["tenant"]) == 1
    assert mock_steps["tenant"][0][1] == "Acme"  # tenant_name
    assert mock_steps["llm"][0][1] == "stub"  # provider
    assert mock_steps["engagement"][0][1] == "Pilot"
    assert mock_steps["user"][0][1] == "kenny"
    assert mock_steps["member"][0][3] == "deployment_strategist"  # default role


def test_skips_member_step_when_user_already_exists(
    mock_steps: dict[str, list[tuple]], monkeypatch: pytest.MonkeyPatch
) -> None:
    # step_user returning None signals 409-conflict (user already exists).
    monkeypatch.setattr(init_mod, "step_user", lambda *a: None)
    rc = init_mod.main(
        [
            "--tenant-name",
            "Acme",
            "--llm-provider",
            "stub",
            "--engagement-name",
            "Pilot",
            "--user-name",
            "kenny",
        ]
    )
    assert rc == 0
    assert mock_steps["member"] == []  # no member call when user wasn't created


def test_stable_tenant_id_passed_through(
    mock_steps: dict[str, list[tuple]], monkeypatch: pytest.MonkeyPatch
) -> None:
    rc = init_mod.main(
        [
            "--tenant-id",
            "11111111-1111-1111-1111-111111111111",
            "--tenant-name",
            "Acme",
            "--llm-provider",
            "stub",
            "--engagement-name",
            "Pilot",
            "--user-name",
            "kenny",
        ]
    )
    assert rc == 0
    # First arg to step_tenant is the tenant_id.
    assert mock_steps["tenant"][0][0] == "11111111-1111-1111-1111-111111111111"
    # And it's threaded into the other steps.
    assert mock_steps["llm"][0][0] == "11111111-1111-1111-1111-111111111111"
    assert mock_steps["engagement"][0][0] == "11111111-1111-1111-1111-111111111111"


def test_invalid_role_rejected_by_argparse() -> None:
    with pytest.raises(SystemExit):
        init_mod.main(
            [
                "--tenant-name",
                "Acme",
                "--llm-provider",
                "stub",
                "--engagement-name",
                "Pilot",
                "--user-name",
                "kenny",
                "--role",
                "wizard",
            ]
        )


def test_invalid_provider_rejected_by_argparse() -> None:
    with pytest.raises(SystemExit):
        init_mod.main(
            [
                "--tenant-name",
                "Acme",
                "--llm-provider",
                "openai-broken",
                "--engagement-name",
                "Pilot",
                "--user-name",
                "kenny",
            ]
        )


def test_http_translates_409_to_none() -> None:
    """`_http_with_409_ok` swallows 409s but re-raises everything else."""

    def boom_409(*_args, **_kwargs):
        raise SystemExit("init: HTTP 409 on POST /thing\nalready exists")

    def boom_500(*_args, **_kwargs):
        raise SystemExit("init: HTTP 500 on POST /thing\nserver error")

    with patch.object(init_mod, "_http", side_effect=boom_409):
        assert init_mod._http_with_409_ok("POST", "/thing") is None
    with patch.object(init_mod, "_http", side_effect=boom_500), pytest.raises(SystemExit) as exc:
        init_mod._http_with_409_ok("POST", "/thing")
    assert "HTTP 500" in str(exc.value)
