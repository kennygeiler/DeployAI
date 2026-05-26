"""Unit tests for ``api_keys`` hash + verify helpers (v2 Phase 4)."""

from __future__ import annotations

import pytest

from control_plane.domain.app_identity.api_keys import (
    RAW_KEY_PREFIX,
    constant_time_eq,
    generate_raw_key,
    hash_raw_key,
    verify_raw_key,
)


def test_generate_raw_key_has_prefix_and_entropy() -> None:
    key = generate_raw_key()
    assert key.startswith(RAW_KEY_PREFIX)
    suffix = key[len(RAW_KEY_PREFIX) :]
    # 24 random bytes hex-encoded => 48 chars
    assert len(suffix) == 48
    # two consecutive keys are unique
    assert generate_raw_key() != generate_raw_key()


def test_hash_then_verify_roundtrip() -> None:
    raw = generate_raw_key()
    hashed = hash_raw_key(raw)
    assert hashed != raw
    assert verify_raw_key(raw, hashed) is True


def test_verify_rejects_wrong_secret() -> None:
    a = generate_raw_key()
    b = generate_raw_key()
    hashed = hash_raw_key(a)
    assert verify_raw_key(b, hashed) is False


def test_verify_rejects_tampered_hash() -> None:
    raw = generate_raw_key()
    hashed = hash_raw_key(raw)
    # flip a character in the encoded derived suffix
    parts = hashed.split("$")
    parts[-1] = parts[-1][:-1] + ("A" if parts[-1][-1] != "A" else "B")
    tampered = "$".join(parts)
    assert verify_raw_key(raw, tampered) is False


def test_verify_rejects_malformed_hash() -> None:
    raw = generate_raw_key()
    assert verify_raw_key(raw, "not-a-real-hash") is False
    assert verify_raw_key(raw, "") is False
    assert verify_raw_key("", hash_raw_key(raw)) is False


def test_two_hashes_of_same_key_differ_via_salt() -> None:
    raw = generate_raw_key()
    h1 = hash_raw_key(raw)
    h2 = hash_raw_key(raw)
    assert h1 != h2
    assert verify_raw_key(raw, h1)
    assert verify_raw_key(raw, h2)


def test_hash_rejects_empty_input() -> None:
    with pytest.raises(ValueError):
        hash_raw_key("")


def test_constant_time_eq_basics() -> None:
    assert constant_time_eq("abc", "abc") is True
    assert constant_time_eq("abc", "abd") is False
    assert constant_time_eq("abc", "abcd") is False
