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

import init as init_mod


@pytest.fixture
def mock_steps(monkeypatch: pytest.MonkeyPatch) -> dict[str, list[tuple]]:
    """Replace each side-effecting step with a recording stub."""
    calls: dict[str, list[tuple]] = {
        "tenant": [],
        "llm": [],
        "engagement": [],
        "user": [],
        "member": [],
        "starter_nodes": [],
        "template_prompts": [],
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
    monkeypatch.setattr(
        init_mod, "step_starter_nodes", lambda *a: calls["starter_nodes"].append(a)
    )
    monkeypatch.setattr(
        init_mod, "step_template_prompts", lambda *a: calls["template_prompts"].append(a)
    )
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


# --- Sprint 7 — industry templates -----------------------------------------


def test_template_fills_engagement_and_customer_defaults(
    mock_steps: dict[str, list[tuple]], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("DEPLOYAI_INIT_ENGAGEMENT_NAME", raising=False)
    monkeypatch.delenv("DEPLOYAI_INIT_CUSTOMER_ACCOUNT", raising=False)
    rc = init_mod.main(
        [
            "--template",
            "gov",
            "--tenant-name",
            "Acme County",
            "--llm-provider",
            "stub",
            "--user-name",
            "kenny",
        ]
    )
    assert rc == 0
    gov_template = init_mod.TEMPLATES["gov"]
    # engagement step receives the template's default name + customer + phase.
    eng_call = mock_steps["engagement"][0]
    assert eng_call[1] == gov_template.default_engagement_name
    assert eng_call[2] == gov_template.default_customer_account
    assert eng_call[3] == gov_template.default_phase
    # starter-nodes + template-prompts steps fire exactly once.
    assert len(mock_steps["starter_nodes"]) == 1
    assert mock_steps["starter_nodes"][0][2] == gov_template.starter_nodes
    assert len(mock_steps["template_prompts"]) == 1
    assert mock_steps["template_prompts"][0][1] == gov_template.agent_prompts


def test_template_overridden_by_explicit_engagement_name(
    mock_steps: dict[str, list[tuple]], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("DEPLOYAI_INIT_ENGAGEMENT_NAME", raising=False)
    rc = init_mod.main(
        [
            "--template",
            "healthcare",
            "--tenant-name",
            "Acme Health",
            "--llm-provider",
            "stub",
            "--user-name",
            "kenny",
            "--engagement-name",
            "Custom rollout name",
            "--customer-account",
            "Custom Account",
        ]
    )
    assert rc == 0
    eng_call = mock_steps["engagement"][0]
    assert eng_call[1] == "Custom rollout name"
    assert eng_call[2] == "Custom Account"


def test_unknown_template_rejected_by_argparse() -> None:
    with pytest.raises(SystemExit) as exc:
        init_mod.main(
            [
                "--template",
                "telecom",
                "--tenant-name",
                "Acme",
                "--llm-provider",
                "stub",
                "--engagement-name",
                "x",
                "--user-name",
                "kenny",
            ]
        )
    # argparse exits 2 on invalid choices.
    assert exc.value.code == 2


def test_no_template_skips_starter_node_and_prompt_steps(
    mock_steps: dict[str, list[tuple]],
) -> None:
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
    assert mock_steps["starter_nodes"] == []
    assert mock_steps["template_prompts"] == []


def test_template_prompts_404_is_gracefully_skipped(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Forward-compat: sibling B1.1's prompt endpoint may not be merged yet."""
    calls: list[tuple[str, str]] = []

    def fake_http(method: str, path: str, body: dict | None = None):
        calls.append((method, path))
        raise SystemExit(f"init: HTTP 404 on {method} {path}\nnot found")

    monkeypatch.setattr(init_mod, "_http", fake_http)
    init_mod.step_template_prompts(
        "11111111-1111-1111-1111-111111111111",
        {"cartographer": "suffix-c", "oracle": "suffix-o"},
    )
    # Both agents attempted; neither raises.
    assert len(calls) == 2
    out = capsys.readouterr().out
    assert "prompt endpoint not yet available" in out


def test_template_prompts_non_404_still_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_http(method: str, path: str, body: dict | None = None):
        raise SystemExit(f"init: HTTP 500 on {method} {path}\nserver blew up")

    monkeypatch.setattr(init_mod, "_http", fake_http)
    with pytest.raises(SystemExit) as exc:
        init_mod.step_template_prompts(
            "11111111-1111-1111-1111-111111111111",
            {"cartographer": "suffix"},
        )
    assert "HTTP 500" in str(exc.value)


def test_all_templates_load_and_match_dataclass() -> None:
    """Each shipped template is a valid `Template` instance with the right
    shape — node_type / phase strings are validated against the CP catalogs
    by the API layer at runtime."""
    assert set(init_mod.TEMPLATES.keys()) == {"gov", "healthcare", "saas", "sales"}
    for name, tpl in init_mod.TEMPLATES.items():
        assert isinstance(tpl, init_mod.Template)
        assert tpl.name == name
        assert tpl.default_engagement_name
        assert tpl.default_customer_account
        assert tpl.default_phase.startswith("P")
        assert 1 <= len(tpl.starter_nodes) <= 10
        for spec in tpl.starter_nodes:
            assert "node_type" in spec and "title" in spec
        assert set(tpl.agent_prompts.keys()) == {
            "cartographer",
            "oracle",
            "master_strategist",
        }
