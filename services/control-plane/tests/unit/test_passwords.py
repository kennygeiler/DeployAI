"""Argon2id hashing helper + password policy (auth/passwords.py)."""

from __future__ import annotations

from control_plane.auth.passwords import (
    DUMMY_HASH,
    PASSWORD_MAX_LENGTH,
    PASSWORD_MIN_LENGTH,
    hash_password,
    needs_rehash,
    password_policy_error,
    verify_password,
)


def test_hash_verify_roundtrip() -> None:
    h = hash_password("correct horse battery staple")
    assert h.startswith("$argon2id$")
    assert verify_password(h, "correct horse battery staple") is True
    assert verify_password(h, "wrong horse battery staple") is False


def test_hash_is_salted_per_call() -> None:
    assert hash_password("same-password-123") != hash_password("same-password-123")


def test_verify_garbage_hash_is_false_not_exception() -> None:
    assert verify_password("not-a-hash", "whatever-password") is False
    assert verify_password("", "whatever-password") is False


def test_dummy_hash_verifies_false_for_any_password() -> None:
    # The anti-enumeration dummy must be a real argon2id hash (so timing is
    # uniform) that never matches a caller-supplied password.
    assert DUMMY_HASH.startswith("$argon2id$")
    assert verify_password(DUMMY_HASH, "any password at all") is False


def test_fresh_hash_needs_no_rehash_and_garbage_does() -> None:
    assert needs_rehash(hash_password("some password 42")) is False
    assert needs_rehash("garbage") is True


def test_policy_min_length() -> None:
    err = password_policy_error("a" * (PASSWORD_MIN_LENGTH - 1))
    assert err is not None and str(PASSWORD_MIN_LENGTH) in err


def test_policy_max_length() -> None:
    err = password_policy_error("a" * (PASSWORD_MAX_LENGTH + 1))
    assert err is not None and str(PASSWORD_MAX_LENGTH) in err


def test_policy_rejects_worst_list_case_insensitively() -> None:
    assert password_policy_error("password123") is not None
    assert password_policy_error("PASSWORD123") is not None


def test_policy_accepts_long_passphrase_without_composition_rules() -> None:
    # No digit / symbol / uppercase requirements — length is the policy.
    assert password_policy_error("correct horse battery staple") is None
    assert password_policy_error("plainlowercasepassphrase") is None
