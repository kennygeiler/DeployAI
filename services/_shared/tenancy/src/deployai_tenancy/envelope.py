"""Envelope-encryption primitives — layer 3 of the NFR23 defense.

A per-tenant Data Encryption Key (DEK) is fetched through a :class:`DEKProvider`
and passed to :func:`encrypt_field` / :func:`decrypt_field` which invoke
pgcrypto's ``pgp_sym_encrypt_bytea`` / ``pgp_sym_decrypt_bytea`` inside the
caller-supplied tenant-scoped session.

Production will ship a ``KMSEnvelopeDEKProvider`` (Story 3.x) that:

1. Calls AWS KMS ``GenerateDataKey(KeySpec=AES_256)`` to mint a fresh DEK per
   encryption (the ciphertext from KMS is stored alongside the encrypted field).
2. Calls ``Decrypt`` on the KMS-encrypted DEK to unwrap on read.
3. Caches unwrapped DEKs in a bounded TTL cache to avoid KMS per-read latency.

For Story 1.9 we ship only :class:`InMemoryDEKProvider` — a deterministic,
dev/test-only derivation of a DEK from the tenant id + a pepper. It is *not*
secure (no KMS, deterministic, same process has the pepper) and is hard-gated
to ``ENVIRONMENT in {dev, test}``.
"""

from __future__ import annotations

import hashlib
import os
from typing import Protocol, runtime_checkable
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from deployai_tenancy.decorators import requires_tenant_scope
from deployai_tenancy.errors import DEKUnavailable

_DEV_ENVIRONMENTS = frozenset({"dev", "test", "ci"})
_DEFAULT_DEV_PEPPER = b"deployai-dev-pepper-not-secret-v1"
_MIN_PEPPER_BYTES = 16
# pgcrypto's pgp_sym_encrypt default cipher is CAST5; we force AES-256 with a
# strong s2k passphrase derivation so the named cipher in the docs matches the
# bytes actually written. s2k-mode=3 = iterated+salted; sha256 digest; high
# iteration count. Full list: https://www.postgresql.org/docs/16/pgcrypto.html
_PGCRYPTO_OPTIONS = "cipher-algo=aes256, s2k-mode=3, s2k-digest-algo=sha256, s2k-count=65011712"


@runtime_checkable
class DEKProvider(Protocol):
    """Per-tenant Data Encryption Key provider.

    Implementations MUST return a 32-byte key suitable for AES-256 (pgcrypto's
    ``pgp_sym_encrypt`` accepts a text password of any length; we hex-encode the
    32 bytes and pass that as the passphrase).
    """

    async def get_dek(self, tenant_id: UUID) -> bytes:  # pragma: no cover - Protocol
        """Return the 32-byte DEK for ``tenant_id``."""
        ...


class InMemoryDEKProvider:
    """Deterministic, dev/test-only DEK derived from tenant id + pepper.

    :raises DEKUnavailable: if ``ENVIRONMENT`` is not one of {dev, test, ci}.

    The derivation is ``SHA-256(tenant_id.bytes || pepper)`` — reproducible
    across restarts (required for dev containers to round-trip encrypted data
    without a KMS dependency) and *explicitly not cryptographically secure* for
    production. The DEKUnavailable guard is checked at construction, not at
    :meth:`get_dek` time, so misconfiguration fails fast at service boot.
    """

    def __init__(self, *, pepper: bytes | None = None, environment: str | None = None) -> None:
        env = environment if environment is not None else os.environ.get("ENVIRONMENT", "dev")
        if env not in _DEV_ENVIRONMENTS:
            raise DEKUnavailable(
                f"InMemoryDEKProvider is dev/test only; ENVIRONMENT='{env}'. "
                "Use KMSEnvelopeDEKProvider in production (Story 3.x).",
            )
        if pepper is not None and len(pepper) < _MIN_PEPPER_BYTES:
            raise DEKUnavailable(
                f"pepper must be at least {_MIN_PEPPER_BYTES} bytes; got {len(pepper)}",
            )
        self._pepper = pepper if pepper is not None else _DEFAULT_DEV_PEPPER

    async def get_dek(self, tenant_id: UUID) -> bytes:
        """Return the 32-byte DEK for ``tenant_id``."""
        return hashlib.sha256(tenant_id.bytes + self._pepper).digest()


def _dek_to_passphrase(dek: bytes) -> str:
    """Hex-encode the DEK so it can be passed as a text passphrase to pgcrypto."""
    if len(dek) != 32:
        raise DEKUnavailable(f"DEK must be 32 bytes; got {len(dek)}")
    return dek.hex()


@requires_tenant_scope
async def encrypt_field(
    session: AsyncSession,
    *,
    plaintext: bytes,
    dek: bytes,
) -> bytes:
    """Encrypt ``plaintext`` with ``dek`` via pgcrypto ``pgp_sym_encrypt_bytea``.

    The call round-trips through the supplied :class:`AsyncSession`, which must
    be tenant-scoped (enforced by :func:`requires_tenant_scope`). We pass the
    explicit ``cipher-algo=aes256`` option so the on-disk bytes actually match
    the "AES-256" described in the architecture doc — pgcrypto's default is
    CAST5, not AES-256.
    """
    passphrase = _dek_to_passphrase(dek)
    result = await session.execute(
        text("SELECT pgp_sym_encrypt_bytea(:pt, :psw, :opts)"),
        {"pt": plaintext, "psw": passphrase, "opts": _PGCRYPTO_OPTIONS},
    )
    value = result.scalar_one()
    if value is None:
        raise DEKUnavailable("encryption returned NULL — unexpected pgcrypto failure")
    return bytes(value)


@requires_tenant_scope
async def decrypt_field(
    session: AsyncSession,
    *,
    ciphertext: bytes,
    dek: bytes,
) -> bytes:
    """Decrypt ``ciphertext`` with ``dek`` via pgcrypto ``pgp_sym_decrypt_bytea``.

    :raises DEKUnavailable: if pgcrypto returns NULL, which indicates either a
        wrong DEK or corrupted ciphertext (pgcrypto swallows the MAC failure
        and returns NULL in some builds — we surface it as a typed exception
        rather than letting ``bytes(None)`` raise an opaque ``TypeError``).
    """
    passphrase = _dek_to_passphrase(dek)
    result = await session.execute(
        text("SELECT pgp_sym_decrypt_bytea(:ct, :psw)"),
        {"ct": ciphertext, "psw": passphrase},
    )
    value = result.scalar_one()
    if value is None:
        raise DEKUnavailable(
            "decryption returned NULL — wrong DEK or corrupted ciphertext",
        )
    return bytes(value)
