from __future__ import annotations

import sys
import types

import pytest


def test_resolve_anthropic_prefers_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "env-key")
    monkeypatch.setenv("DEPLOYAI_ANTHROPIC_SECRET_ARN", "arn:aws:secretsmanager:us-east-1:1:secret:x")
    from llm_provider_py.secrets import resolve_anthropic_api_key

    assert resolve_anthropic_api_key() == "env-key"


def test_get_secret_string_uses_boto3(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    class FakeClient:
        def get_secret_value(self, **kwargs: str) -> dict[str, str]:
            assert kwargs.get("SecretId") == "arn:aws:x"
            return {"SecretString": "secret-value"}

    def fake_client(name: str, **kwargs: object) -> FakeClient:
        assert name == "secretsmanager"
        return FakeClient()

    fake_boto = types.ModuleType("boto3")
    fake_boto.client = fake_client  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "boto3", fake_boto)

    from llm_provider_py.secrets import get_secret_string

    assert get_secret_string("arn:aws:x") == "secret-value"
