"""Envelope-encryption unit tests — DEK provider behavior + helper shape."""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from deployai_tenancy import DEKProvider, DEKUnavailable, InMemoryDEKProvider
from deployai_tenancy.envelope import _dek_to_passphrase, decrypt_field, encrypt_field
from deployai_tenancy.errors import MissingTenantScope
from deployai_tenancy.session import TENANT_SCOPED_KEY

_TENANT = uuid.UUID("33333333-3333-3333-3333-333333333333")


def test_in_memory_provider_protocol_conformance() -> None:
    """``InMemoryDEKProvider`` is a structural match for ``DEKProvider``."""
    provider = InMemoryDEKProvider(environment="dev")
    assert isinstance(provider, DEKProvider)


async def test_in_memory_provider_deterministic() -> None:
    provider = InMemoryDEKProvider(environment="dev")
    dek1 = await provider.get_dek(_TENANT)
    dek2 = await provider.get_dek(_TENANT)
    assert dek1 == dek2
    assert len(dek1) == 32


async def test_in_memory_provider_different_tenants_different_keys() -> None:
    provider = InMemoryDEKProvider(environment="dev")
    other = uuid.UUID("44444444-4444-4444-4444-444444444444")
    assert await provider.get_dek(_TENANT) != await provider.get_dek(other)


async def test_in_memory_provider_pepper_affects_output() -> None:
    p1 = InMemoryDEKProvider(environment="dev", pepper=b"a" * 16)
    p2 = InMemoryDEKProvider(environment="dev", pepper=b"b" * 16)
    assert await p1.get_dek(_TENANT) != await p2.get_dek(_TENANT)


def test_in_memory_provider_blocks_prod() -> None:
    with pytest.raises(DEKUnavailable, match=r"Story 3\.x"):
        InMemoryDEKProvider(environment="prod")


def test_in_memory_provider_blocks_staging() -> None:
    with pytest.raises(DEKUnavailable):
        InMemoryDEKProvider(environment="staging")


def test_in_memory_provider_respects_env_var(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "prod")
    with pytest.raises(DEKUnavailable):
        InMemoryDEKProvider()


def test_dek_to_passphrase_rejects_wrong_length() -> None:
    with pytest.raises(DEKUnavailable, match="32 bytes"):
        _dek_to_passphrase(b"short")


def test_dek_to_passphrase_hex_encodes() -> None:
    dek = b"\x00" * 32
    assert _dek_to_passphrase(dek) == "00" * 32


async def _scoped_session() -> AsyncSession:
    """Minimal ``AsyncSession`` mock tagged as tenant-scoped."""
    session = MagicMock(spec=AsyncSession)
    session.info = {TENANT_SCOPED_KEY: True}
    execute_result = MagicMock()
    execute_result.scalar_one.return_value = b"\xde\xad\xbe\xef"

    async def _execute(*_: object, **__: object) -> object:
        return execute_result

    session.execute = _execute  # type: ignore[assignment]
    return session


async def test_encrypt_field_requires_tenant_scope() -> None:
    raw_session = MagicMock(spec=AsyncSession)
    raw_session.info = {}
    with pytest.raises(MissingTenantScope):
        await encrypt_field(raw_session, plaintext=b"x", dek=b"\x00" * 32)


async def test_decrypt_field_requires_tenant_scope() -> None:
    raw_session = MagicMock(spec=AsyncSession)
    raw_session.info = {}
    with pytest.raises(MissingTenantScope):
        await decrypt_field(raw_session, ciphertext=b"x", dek=b"\x00" * 32)


async def test_encrypt_field_passes_hex_passphrase() -> None:
    calls: list[tuple[object, dict[str, object]]] = []
    session = MagicMock(spec=AsyncSession)
    session.info = {TENANT_SCOPED_KEY: True}

    execute_result = MagicMock()
    execute_result.scalar_one.return_value = b"\xaa\xbb"

    async def _execute(stmt: object, params: dict[str, object]) -> object:
        calls.append((stmt, params))
        return execute_result

    session.execute = _execute  # type: ignore[assignment]

    out = await encrypt_field(session, plaintext=b"hello", dek=b"\x01" * 32)
    assert out == b"\xaa\xbb"
    assert len(calls) == 1
    params = calls[0][1]
    assert params["pt"] == b"hello"
    assert params["psw"] == "01" * 32


async def test_encrypt_rejects_wrong_length_dek() -> None:
    session = MagicMock(spec=AsyncSession)
    session.info = {TENANT_SCOPED_KEY: True}
    with pytest.raises(DEKUnavailable, match="32 bytes"):
        await encrypt_field(session, plaintext=b"x", dek=b"short")


def test_in_memory_provider_rejects_short_pepper() -> None:
    with pytest.raises(DEKUnavailable, match="at least"):
        InMemoryDEKProvider(environment="dev", pepper=b"")
    with pytest.raises(DEKUnavailable, match="at least"):
        InMemoryDEKProvider(environment="dev", pepper=b"too-short")


async def test_decrypt_field_null_ciphertext_raises_domain_exception() -> None:
    """A NULL result (wrong DEK / corrupted ct) must surface as ``DEKUnavailable``."""
    session = MagicMock(spec=AsyncSession)
    session.info = {TENANT_SCOPED_KEY: True}

    execute_result = MagicMock()
    execute_result.scalar_one.return_value = None

    async def _execute(*_: object, **__: object) -> object:
        return execute_result

    session.execute = _execute  # type: ignore[assignment]

    with pytest.raises(DEKUnavailable, match="decryption returned NULL"):
        await decrypt_field(session, ciphertext=b"\xaa", dek=b"\x00" * 32)


async def test_fake_roundtrip_through_stub_executor() -> None:
    """AC7 — ``encrypt_field(decrypt_field(ct, dek), dek) == plaintext`` via stub.

    We fake pgcrypto as an XOR-with-passphrase-byte dummy so the helpers actually
    round-trip through the executor. Proves the helper signatures and the
    session.execute interaction shape compose correctly.
    """
    session = MagicMock(spec=AsyncSession)
    session.info = {TENANT_SCOPED_KEY: True}

    async def _execute(stmt: object, params: dict[str, object]) -> object:
        result = MagicMock()
        psw = params["psw"]
        assert isinstance(psw, str)
        key_byte = int(psw[:2], 16) & 0xFF
        sql = str(stmt)
        if "encrypt" in sql:
            pt = params["pt"]
            assert isinstance(pt, bytes)
            result.scalar_one.return_value = bytes(b ^ key_byte for b in pt)
        else:
            ct = params["ct"]
            assert isinstance(ct, bytes)
            result.scalar_one.return_value = bytes(b ^ key_byte for b in ct)
        return result

    session.execute = _execute  # type: ignore[assignment]

    plaintext = b"sensitive evidence"
    dek = b"\x42" * 32
    ct = await encrypt_field(session, plaintext=plaintext, dek=dek)
    recovered = await decrypt_field(session, ciphertext=ct, dek=dek)
    assert recovered == plaintext
