"""Unit tests for the real integration kill switch (pilot-refresh ticket A8).

Provider revocation paths run against ``httpx.MockTransport`` so no
network is touched. The end-to-end ``disable_integration`` tests drive a
scripted fake ``AsyncSession`` (same approach as ``test_embedder_tick``)
and assert the three phase ledger events land with the right kinds.
Real-database purge coverage lives in
``tests/integration/test_integration_kill_switch_db.py``.
"""

from __future__ import annotations

import json
import uuid
from typing import Any
from unittest.mock import MagicMock

import httpx
import pytest

from control_plane.domain.integrations.models import Integration
from control_plane.domain.ledger import LedgerEvent
from control_plane.integrations.oauth_revocation import (
    GOOGLE_REVOKE_URL,
    SLACK_REVOKE_URL,
    microsoft_revocation_posture,
    revoke_google_token,
    revoke_provider_tokens,
    revoke_slack_token,
)
from control_plane.services.integration_kill_switch import disable_integration

# ---------------------------------------------------------------------------
# httpx harness
# ---------------------------------------------------------------------------


def _client(handler: Any) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def _recording_handler(status_code: int, body: Any = "", requests: list[httpx.Request] | None = None) -> Any:
    def handle(request: httpx.Request) -> httpx.Response:
        if requests is not None:
            requests.append(request)
        content = json.dumps(body) if isinstance(body, dict) else str(body)
        return httpx.Response(status_code, content=content)

    return handle


# ---------------------------------------------------------------------------
# Google
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_google_revoke_success() -> None:
    seen: list[httpx.Request] = []
    async with _client(_recording_handler(200, requests=seen)) as c:
        res = await revoke_google_token(c, token="rt-123")
    assert res.outcome == "revoked" and res.ok
    assert str(seen[0].url) == GOOGLE_REVOKE_URL
    assert b"token=rt-123" in seen[0].content


@pytest.mark.asyncio
async def test_google_revoke_already_revoked_400_is_success_with_note() -> None:
    async with _client(_recording_handler(400, {"error": "invalid_token"})) as c:
        res = await revoke_google_token(c, token="rt-dead")
    assert res.outcome == "already_revoked" and res.ok
    assert res.http_status == 400


@pytest.mark.asyncio
async def test_google_revoke_hard_failure_5xx() -> None:
    async with _client(_recording_handler(503)) as c:
        res = await revoke_google_token(c, token="rt-123")
    assert res.outcome == "failed" and not res.ok


@pytest.mark.asyncio
async def test_google_revoke_transport_error_is_failed_not_raised() -> None:
    def boom(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no route", request=request)

    async with _client(boom) as c:
        res = await revoke_google_token(c, token="rt-123")
    assert res.outcome == "failed"


@pytest.mark.asyncio
async def test_google_revoke_empty_token_skipped() -> None:
    async with _client(_recording_handler(200)) as c:
        res = await revoke_google_token(c, token="")
    assert res.outcome == "skipped" and res.ok


# ---------------------------------------------------------------------------
# Slack
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_slack_revoke_success_sends_bearer() -> None:
    seen: list[httpx.Request] = []
    async with _client(_recording_handler(200, {"ok": True, "revoked": True}, requests=seen)) as c:
        res = await revoke_slack_token(c, token="xoxb-1")
    assert res.outcome == "revoked" and res.ok
    assert str(seen[0].url) == SLACK_REVOKE_URL
    assert seen[0].headers["Authorization"] == "Bearer xoxb-1"


@pytest.mark.asyncio
@pytest.mark.parametrize("err", ["invalid_auth", "token_revoked", "account_inactive"])
async def test_slack_revoke_already_dead_errors_are_success_with_note(err: str) -> None:
    async with _client(_recording_handler(200, {"ok": False, "error": err})) as c:
        res = await revoke_slack_token(c, token="xoxb-1")
    assert res.outcome == "already_revoked" and res.ok
    assert err in res.note


@pytest.mark.asyncio
async def test_slack_revoke_other_api_error_is_failed() -> None:
    async with _client(_recording_handler(200, {"ok": False, "error": "ratelimited"})) as c:
        res = await revoke_slack_token(c, token="xoxb-1")
    assert res.outcome == "failed" and not res.ok


@pytest.mark.asyncio
async def test_slack_revoke_http_5xx_is_failed() -> None:
    async with _client(_recording_handler(500)) as c:
        res = await revoke_slack_token(c, token="xoxb-1")
    assert res.outcome == "failed"


# ---------------------------------------------------------------------------
# Microsoft + dispatch
# ---------------------------------------------------------------------------


def test_microsoft_posture_unsupported_with_tokens() -> None:
    res = microsoft_revocation_posture(has_tokens=True)
    assert res.outcome == "unsupported" and res.ok
    assert "invalidateAllRefreshTokens" in res.note


def test_microsoft_posture_skipped_without_tokens() -> None:
    assert microsoft_revocation_posture(has_tokens=False).outcome == "skipped"


@pytest.mark.asyncio
async def test_dispatch_google_prefers_refresh_token() -> None:
    seen: list[httpx.Request] = []
    async with _client(_recording_handler(200, requests=seen)) as c:
        res = await revoke_provider_tokens(
            c, provider="google_gmail", oauth_config={"refresh_token": "rt-x", "access_token": "at-y"}
        )
    assert res.outcome == "revoked"
    assert b"token=rt-x" in seen[0].content


@pytest.mark.asyncio
@pytest.mark.parametrize("provider", ["m365_calendar", "m365_mail", "m365_teams"])
async def test_dispatch_microsoft_never_calls_network(provider: str) -> None:
    def explode(request: httpx.Request) -> httpx.Response:
        raise AssertionError("Microsoft path must not make HTTP calls")

    async with _client(explode) as c:
        res = await revoke_provider_tokens(c, provider=provider, oauth_config={"refresh_token": "rt"})
    assert res.outcome == "unsupported" and res.ok


@pytest.mark.asyncio
async def test_dispatch_unknown_provider_is_skipped() -> None:
    async with _client(_recording_handler(200)) as c:
        res = await revoke_provider_tokens(c, provider="jira", oauth_config={})
    assert res.outcome == "skipped" and res.ok


# ---------------------------------------------------------------------------
# disable_integration end-to-end (fake session)
# ---------------------------------------------------------------------------


class _FakeResult:
    def __init__(self, row: Integration | None = None, rowcount: int = 0) -> None:
        self._row = row
        self.rowcount = rowcount

    def scalar_one_or_none(self) -> Integration | None:
        return self._row


class _FakeSession:
    """Scripted AsyncSession: SELECT returns the row, DML returns rowcounts."""

    def __init__(self, row: Integration | None) -> None:
        self._row = row
        self.added: list[Any] = []
        self.committed = False
        self.add = MagicMock(side_effect=self.added.append)
        self.dml_statements: list[Any] = []

    async def execute(self, stmt: Any, params: dict[str, Any] | None = None) -> _FakeResult:
        if stmt.is_select:
            return _FakeResult(row=self._row)
        self.dml_statements.append(stmt)
        return _FakeResult(rowcount=3)

    async def flush(self) -> None:
        pass

    async def commit(self) -> None:
        self.committed = True

    async def refresh(self, obj: Any) -> None:
        pass


def _integration(provider: str = "google_gmail", *, oauth: dict[str, Any] | None = None) -> Integration:
    row = Integration(
        tenant_id=uuid.uuid4(),
        provider=provider,
        display_name="Test",
        state="active",
        config={"oauth": oauth if oauth is not None else {"refresh_token": "rt-1", "access_token": "at-1"}},
    )
    row.id = uuid.uuid4()
    return row


def _ledger_kinds(session: _FakeSession) -> list[str]:
    return [e.source_kind for e in session.added if isinstance(e, LedgerEvent)]


@pytest.mark.asyncio
async def test_disable_emits_all_three_phase_events_on_success() -> None:
    row = _integration()
    session = _FakeSession(row)
    async with _client(_recording_handler(200)) as c:
        out = await disable_integration(session, row.id, http_client=c)  # type: ignore[arg-type]
    assert out["ok"] is True
    assert _ledger_kinds(session) == [
        "killswitch_oauth_revoked",
        "killswitch_queue_purged",
        "killswitch_secrets_deleted",
    ]
    assert row.state == "disabled"
    assert "oauth" not in row.config
    assert session.committed
    # embedding_jobs delete + ingestion_runs update both issued
    assert len(session.dml_statements) == 2
    assert out["oauth_revocation"]["outcome"] == "revoked"


@pytest.mark.asyncio
async def test_disable_emits_failure_kind_but_still_kills_on_provider_5xx() -> None:
    row = _integration()
    session = _FakeSession(row)
    async with _client(_recording_handler(503)) as c:
        out = await disable_integration(session, row.id, http_client=c)  # type: ignore[arg-type]
    assert out["ok"] is True
    kinds = _ledger_kinds(session)
    assert kinds[0] == "killswitch_oauth_revoke_failed"
    assert "killswitch_secrets_deleted" in kinds
    # Kill switch must complete regardless of provider health.
    assert row.state == "disabled"
    assert "oauth" not in row.config


@pytest.mark.asyncio
async def test_disable_microsoft_records_unsupported_revocation_and_deletes_tokens() -> None:
    row = _integration(provider="m365_mail")
    session = _FakeSession(row)

    def explode(request: httpx.Request) -> httpx.Response:
        raise AssertionError("m365 must not hit the network")

    async with _client(explode) as c:
        out = await disable_integration(session, row.id, http_client=c)  # type: ignore[arg-type]
    assert out["oauth_revocation"]["outcome"] == "unsupported"
    assert "invalidateAllRefreshTokens" in out["oauth_revocation"]["note"]
    assert _ledger_kinds(session)[0] == "killswitch_oauth_revoked"
    assert "oauth" not in row.config


@pytest.mark.asyncio
async def test_disable_slack_already_revoked_counts_as_success() -> None:
    row = _integration(provider="slack", oauth={"access_token": "xoxb-9"})
    session = _FakeSession(row)
    async with _client(_recording_handler(200, {"ok": False, "error": "token_revoked"})) as c:
        out = await disable_integration(session, row.id, http_client=c)  # type: ignore[arg-type]
    assert out["oauth_revocation"]["outcome"] == "already_revoked"
    assert _ledger_kinds(session)[0] == "killswitch_oauth_revoked"


@pytest.mark.asyncio
async def test_disable_missing_row_returns_not_found() -> None:
    session = _FakeSession(None)
    out = await disable_integration(session, uuid.uuid4())  # type: ignore[arg-type]
    assert out == {"not_found": True}
    assert _ledger_kinds(session) == []


@pytest.mark.asyncio
async def test_disable_already_disabled_is_idempotent_no_events() -> None:
    row = _integration()
    row.state = "disabled"
    session = _FakeSession(row)
    out = await disable_integration(session, row.id)  # type: ignore[arg-type]
    assert out["already_disabled"] is True
    assert _ledger_kinds(session) == []


@pytest.mark.asyncio
async def test_ledger_details_never_contain_token_values() -> None:
    row = _integration()
    session = _FakeSession(row)
    async with _client(_recording_handler(200)) as c:
        await disable_integration(session, row.id, http_client=c)  # type: ignore[arg-type]
    for event in (e for e in session.added if isinstance(e, LedgerEvent)):
        blob = json.dumps(event.detail)
        assert "rt-1" not in blob
        assert "at-1" not in blob
