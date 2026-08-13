"""ASGI unit tests for /api/v1/auth (signup gate, login uniformity, limiter, invites).

No Postgres/Redis: the DB dependency is overridden with a fake session, the
session mint + ledger emit are monkeypatched, and the attempt limiter runs on
its in-memory backend. Full-stack behavior lives in
tests/integration/test_auth_account_flow.py.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient

import control_plane.api.routes.auth_account as mod
from control_plane.api.routes.auth import bearer_access_claims
from control_plane.auth.passwords import hash_password
from control_plane.auth.session_service import SessionPair
from control_plane.config.settings import clear_settings_cache
from control_plane.db import get_app_db_session
from control_plane.domain.app_identity.models import AppTenant, AppUser, UserInvite
from control_plane.main import app

TENANT_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")
USER_ID = uuid.UUID("22222222-2222-2222-2222-222222222222")
GOOD_PASSWORD = "a strong enough passphrase"


class _FakeResult:
    def __init__(self, rows: list[Any]) -> None:
        self._rows = rows

    def scalar_one_or_none(self) -> Any:
        return self._rows[0] if self._rows else None

    def scalars(self) -> Any:
        rows = self._rows

        class _S:
            def all(self) -> list[Any]:
                return rows

        return _S()


class FakeSession:
    """Just enough AsyncSession for these routes: execute -> canned rows,
    get -> canned identity map, add/flush/commit -> recorded no-ops."""

    def __init__(self) -> None:
        self.rows_by_model: dict[type, list[Any]] = {}
        self.identity: dict[tuple[type, uuid.UUID], Any] = {}
        self.added: list[Any] = []
        self.commits = 0

    async def execute(self, stmt: Any) -> _FakeResult:
        model = stmt.column_descriptions[0]["entity"]
        rows = list(self.rows_by_model.get(model, []))
        # Honor the one WHERE clause these routes actually key on: the invite
        # token hash. Everything else stays canned.
        wc = getattr(stmt, "whereclause", None)
        where = "" if wc is None else str(wc)
        if model is UserInvite and "token_hash" in where:
            vals = set(stmt.compile().params.values())
            rows = [r for r in rows if r.token_hash in vals]
        return _FakeResult(rows)

    async def get(self, model: type, pk: uuid.UUID) -> Any:
        return self.identity.get((model, pk))

    def add(self, obj: Any) -> None:
        self.added.append(obj)
        if getattr(obj, "id", None) is None and hasattr(obj, "id"):
            try:
                obj.id = uuid.uuid4()
            except Exception:
                pass

    async def flush(self) -> None:
        return None

    async def commit(self) -> None:
        self.commits += 1

    async def rollback(self) -> None:
        return None


@pytest.fixture(autouse=True)
def _clean() -> Iterator[None]:
    clear_settings_cache()
    mod.reset_auth_attempt_limiter()
    yield
    app.dependency_overrides.clear()
    clear_settings_cache()
    mod.reset_auth_attempt_limiter()


@pytest.fixture()
def fake_session(monkeypatch: pytest.MonkeyPatch) -> FakeSession:
    monkeypatch.delenv("DEPLOYAI_REDIS_URL", raising=False)
    fs = FakeSession()

    async def _dep() -> Any:
        yield fs

    app.dependency_overrides[get_app_db_session] = _dep

    async def _no_ledger(*a: Any, **k: Any) -> None:
        return None

    monkeypatch.setattr(mod, "_emit_auth_ledger", _no_ledger)

    async def _fake_issue(
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
        roles: list[str],
        *,
        access_ttl_seconds: int | None = None,
    ) -> SessionPair:
        return SessionPair(access_token="jwt-x", refresh_jti="refresh-x", expires_in=900)

    monkeypatch.setattr(mod, "issue_tokens", _fake_issue)
    return fs


def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://t")


def _credentialed_user(password: str = GOOD_PASSWORD) -> AppUser:
    return AppUser(
        id=USER_ID,
        tenant_id=TENANT_ID,
        user_name="kim@example.com",
        email="kim@example.com",
        given_name="Kim",
        active=True,
        roles=["customer_admin"],
        password_hash=hash_password(password),
    )


# --- signup gate ------------------------------------------------------------


@pytest.mark.asyncio
async def test_signup_404_when_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DEPLOYAI_SELF_SERVE_SIGNUP", raising=False)
    clear_settings_cache()
    async with _client() as c:
        r = await c.post(
            "/api/v1/auth/signup",
            json={
                "email": "a@b.co",
                "password": GOOD_PASSWORD,
                "workspace_name": "Acme",
                "display_name": "A",
            },
        )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_signup_rejects_weak_password_when_enabled(
    monkeypatch: pytest.MonkeyPatch, fake_session: FakeSession
) -> None:
    monkeypatch.setenv("DEPLOYAI_SELF_SERVE_SIGNUP", "1")
    clear_settings_cache()
    async with _client() as c:
        r = await c.post(
            "/api/v1/auth/signup",
            json={
                "email": "a@b.co",
                "password": "short1",
                "workspace_name": "Acme",
                "display_name": "A",
            },
        )
    assert r.status_code == 422
    assert "at least 10" in r.json()["detail"]


# --- login: enumeration uniformity -----------------------------------------


@pytest.mark.asyncio
async def test_login_unknown_email_and_wrong_password_are_identical(
    fake_session: FakeSession,
) -> None:
    async with _client() as c:
        unknown = await c.post(
            "/api/v1/auth/login",
            json={"email": "nobody@example.com", "password": "whatever pass"},
        )
        fake_session.rows_by_model[AppUser] = [_credentialed_user()]
        wrong = await c.post(
            "/api/v1/auth/login",
            json={"email": "kim@example.com", "password": "not the password"},
        )
    assert unknown.status_code == wrong.status_code == 401
    assert unknown.json() == wrong.json()
    # Neither response leaks a session cookie.
    assert "set-cookie" not in unknown.headers
    assert "set-cookie" not in wrong.headers


@pytest.mark.asyncio
async def test_login_success_issues_session_and_cookies(fake_session: FakeSession) -> None:
    fake_session.rows_by_model[AppUser] = [_credentialed_user()]
    async with _client() as c:
        r = await c.post(
            "/api/v1/auth/login",
            json={"email": "kim@example.com", "password": GOOD_PASSWORD},
        )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["access_token"] == "jwt-x"
    assert body["refresh_token"] == "refresh-x"
    assert body["tenant_id"] == str(TENANT_ID)
    assert body["roles"] == ["customer_admin"]
    cookies = r.headers.get_list("set-cookie")
    assert any(c0.startswith("dep_access=") for c0 in cookies)
    assert any(c0.startswith("dep_refresh=") for c0 in cookies)


@pytest.mark.asyncio
async def test_login_email_lookup_is_case_insensitive_input(fake_session: FakeSession) -> None:
    fake_session.rows_by_model[AppUser] = [_credentialed_user()]
    async with _client() as c:
        r = await c.post(
            "/api/v1/auth/login",
            json={"email": "KIM@EXAMPLE.COM", "password": GOOD_PASSWORD},
        )
    assert r.status_code == 200


# --- attempt limiter --------------------------------------------------------


@pytest.mark.asyncio
async def test_login_attempt_limiter_trips_with_generic_429(fake_session: FakeSession) -> None:
    async with _client() as c:
        for _ in range(10):
            r = await c.post(
                "/api/v1/auth/login",
                json={"email": "nobody@example.com", "password": "whatever pass"},
            )
            assert r.status_code == 401
        r = await c.post(
            "/api/v1/auth/login",
            json={"email": "nobody@example.com", "password": "whatever pass"},
        )
    assert r.status_code == 429
    assert r.json()["detail"] == "too many attempts; try again later"


# --- invites ----------------------------------------------------------------


def _override_claims(roles: list[str]) -> None:
    def _claims() -> dict[str, object]:
        return {"sub": str(USER_ID), "tid": str(TENANT_ID), "roles": roles, "token_use": "access"}

    app.dependency_overrides[bearer_access_claims] = _claims


@pytest.mark.asyncio
async def test_invite_create_requires_admin_role(fake_session: FakeSession) -> None:
    _override_claims(["deployment_strategist"])
    async with _client() as c:
        r = await c.post("/api/v1/auth/invites", json={"email": "x@y.co", "role": "fde"})
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_invite_create_rejects_non_invitable_roles(fake_session: FakeSession) -> None:
    _override_claims(["customer_admin"])
    async with _client() as c:
        r = await c.post("/api/v1/auth/invites", json={"email": "x@y.co", "role": "platform_admin"})
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_invite_token_lifecycle_create_preview_accept_then_dead(
    fake_session: FakeSession,
) -> None:
    """Raw token appears once; hash-at-rest resolves it; used/expired die as 404."""
    _override_claims(["customer_admin"])
    async with _client() as c:
        created = await c.post(
            "/api/v1/auth/invites",
            json={"email": "new@example.com", "role": "deployment_strategist"},
        )
        assert created.status_code == 201, created.text
        join_path = created.json()["join_path"]
        assert join_path.startswith("/join/")
        token = join_path.removeprefix("/join/")

        # The stored row carries only the SHA-256 of the token.
        invite = next(o for o in fake_session.added if isinstance(o, UserInvite))
        assert token not in (invite.token_hash or "")
        assert invite.token_hash == mod._hash_invite_token(token)

        # Preview resolves by hash.
        fake_session.rows_by_model[UserInvite] = [invite]
        fake_session.identity[(AppTenant, TENANT_ID)] = AppTenant(id=TENANT_ID, name="Acme")
        preview = await c.get("/api/v1/auth/invites/preview", params={"token": token})
        assert preview.status_code == 200
        assert preview.json()["email"] == "new@example.com"
        assert preview.json()["workspace_name"] == "Acme"

        # Unknown token -> same generic 404.
        assert (await c.get("/api/v1/auth/invites/preview", params={"token": "nope"})).status_code == 404

        # Accept mints a session, marks the invite used…
        accept = await c.post(
            "/api/v1/auth/invites/accept",
            json={"token": token, "password": GOOD_PASSWORD, "display_name": "New Person"},
        )
        assert accept.status_code == 201, accept.text
        assert accept.json()["roles"] == ["deployment_strategist"]
        assert invite.accepted_at is not None

        # …and a used invite is dead for preview AND accept.
        assert (await c.get("/api/v1/auth/invites/preview", params={"token": token})).status_code == 404
        again = await c.post(
            "/api/v1/auth/invites/accept",
            json={"token": token, "password": GOOD_PASSWORD, "display_name": "Replay"},
        )
        assert again.status_code == 404


@pytest.mark.asyncio
async def test_expired_invite_is_404(fake_session: FakeSession) -> None:
    token = "expired-token"
    fake_session.rows_by_model[UserInvite] = [
        UserInvite(
            id=uuid.uuid4(),
            tenant_id=TENANT_ID,
            email="late@example.com",
            role="fde",
            token_hash=mod._hash_invite_token(token),
            expires_at=datetime.now(UTC) - timedelta(days=1),
        )
    ]
    async with _client() as c:
        r = await c.get("/api/v1/auth/invites/preview", params={"token": token})
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_accept_with_weak_password_is_422(fake_session: FakeSession) -> None:
    token = "live-token"
    fake_session.rows_by_model[UserInvite] = [
        UserInvite(
            id=uuid.uuid4(),
            tenant_id=TENANT_ID,
            email="p@example.com",
            role="fde",
            token_hash=mod._hash_invite_token(token),
            expires_at=datetime.now(UTC) + timedelta(days=1),
        )
    ]
    async with _client() as c:
        r = await c.post(
            "/api/v1/auth/invites/accept",
            json={"token": token, "password": "short1", "display_name": "P"},
        )
    assert r.status_code == 422
