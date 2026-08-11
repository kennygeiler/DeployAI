"""Unit: centralized internal-API auth dependencies (pilot-refresh A4).

Covers the pure resolution logic of ``config/internal_auth.py`` with a fake
session; the real Postgres lookup path is covered by
``tests/integration/test_service_tokens_internal.py``.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from typing import Any

import pytest
from fastapi import HTTPException

from control_plane.config.internal_auth import (
    require_internal,
    require_tenant_scoped,
)
from control_plane.domain.app_identity.service_tokens import (
    RAW_TOKEN_PREFIX,
    generate_raw_token,
    hash_service_token,
)

_TENANT_A = uuid.UUID("00000000-0000-7000-8000-00000000000a")
_TENANT_B = uuid.UUID("00000000-0000-7000-8000-00000000000b")


@dataclass
class _FakeResult:
    row: Any

    def scalar_one_or_none(self) -> Any:
        return self.row


@dataclass
class _FakeSession:
    """Stands in for AsyncSession; returns a canned token row (or None)."""

    row: Any = None
    executed: list[Any] = field(default_factory=list)

    async def execute(self, stmt: Any) -> _FakeResult:
        self.executed.append(stmt)
        return _FakeResult(self.row)


@dataclass
class _FakeToken:
    id: uuid.UUID
    tenant_id: uuid.UUID


@pytest.fixture()
def global_key(monkeypatch: pytest.MonkeyPatch) -> str:
    key = "unit-test-global-key"
    monkeypatch.setenv("DEPLOYAI_INTERNAL_API_KEY", key)
    return key


class TestRequireInternal:
    def test_valid_global_key_passes(self, global_key: str) -> None:
        assert require_internal(global_key) is None

    def test_missing_header_rejected(self, global_key: str) -> None:
        with pytest.raises(HTTPException) as exc:
            require_internal(None)
        assert exc.value.status_code == 401

    def test_wrong_key_rejected(self, global_key: str) -> None:
        with pytest.raises(HTTPException) as exc:
            require_internal("not-the-key")
        assert exc.value.status_code == 401


class TestRequireTenantScoped:
    @pytest.mark.asyncio
    async def test_legacy_global_key_allowed_with_warning(
        self, global_key: str, caplog: pytest.LogCaptureFixture
    ) -> None:
        session = _FakeSession()
        with caplog.at_level(logging.WARNING, logger="control_plane.config.internal_auth"):
            principal = await require_tenant_scoped(session, _TENANT_A, global_key)  # type: ignore[arg-type]
        assert principal.mode == "legacy_global_key"
        assert principal.tenant_id is None
        assert any("legacy_global_key_used" in rec.message for rec in caplog.records)
        # Legacy path must not touch the token table.
        assert session.executed == []

    @pytest.mark.asyncio
    async def test_matching_service_token_passes(self, global_key: str) -> None:
        token = _FakeToken(id=uuid.uuid4(), tenant_id=_TENANT_A)
        session = _FakeSession(row=token)
        principal = await require_tenant_scoped(session, _TENANT_A, "dpai_svc_abc")  # type: ignore[arg-type]
        assert principal.mode == "tenant_service_token"
        assert principal.tenant_id == _TENANT_A
        assert principal.token_id == token.id

    @pytest.mark.asyncio
    async def test_tenant_mismatch_403(self, global_key: str) -> None:
        session = _FakeSession(row=_FakeToken(id=uuid.uuid4(), tenant_id=_TENANT_B))
        with pytest.raises(HTTPException) as exc:
            await require_tenant_scoped(session, _TENANT_A, "dpai_svc_abc")  # type: ignore[arg-type]
        assert exc.value.status_code == 403

    @pytest.mark.asyncio
    async def test_unknown_token_401(self, global_key: str) -> None:
        session = _FakeSession(row=None)
        with pytest.raises(HTTPException) as exc:
            await require_tenant_scoped(session, _TENANT_A, "dpai_svc_bogus")  # type: ignore[arg-type]
        assert exc.value.status_code == 401

    @pytest.mark.asyncio
    async def test_missing_header_401(self, global_key: str) -> None:
        session = _FakeSession()
        with pytest.raises(HTTPException) as exc:
            await require_tenant_scoped(session, _TENANT_A, None)  # type: ignore[arg-type]
        assert exc.value.status_code == 401

    @pytest.mark.asyncio
    async def test_no_global_key_configured_still_resolves_tokens(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """With no legacy key in the env, only service tokens authenticate."""
        monkeypatch.delenv("DEPLOYAI_INTERNAL_API_KEY", raising=False)
        token = _FakeToken(id=uuid.uuid4(), tenant_id=_TENANT_A)
        session = _FakeSession(row=token)
        principal = await require_tenant_scoped(session, _TENANT_A, "dpai_svc_abc")  # type: ignore[arg-type]
        assert principal.mode == "tenant_service_token"


class TestTokenHashing:
    def test_generate_raw_token_shape(self) -> None:
        raw = generate_raw_token()
        assert raw.startswith(RAW_TOKEN_PREFIX)
        assert len(raw) == len(RAW_TOKEN_PREFIX) + 48  # 24 bytes hex-encoded

    def test_hash_is_deterministic_and_hex(self) -> None:
        raw = generate_raw_token()
        digest = hash_service_token(raw)
        assert digest == hash_service_token(raw)
        assert len(digest) == 64
        int(digest, 16)  # raises if not hex

    def test_hash_rejects_empty(self) -> None:
        with pytest.raises(ValueError, match="non-empty"):
            hash_service_token("")
