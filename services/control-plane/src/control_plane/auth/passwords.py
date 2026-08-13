"""Password hashing (argon2id) + policy for native email/password auth.

Parameters are pinned explicitly rather than trusting library defaults so a
future argon2-cffi upgrade cannot silently weaken (or DoS) the login path:

- ``time_cost=3``, ``memory_cost=64 MiB``, ``parallelism=4`` — the OWASP
  password-storage recommendation for argon2id as of 2025; ~40-80 ms per
  verify on current server cores, which also serves as a natural brute-force
  brake on top of the explicit attempt limiter.
- Hashes are self-describing (``$argon2id$v=19$m=65536,t=3,p=4$...``), so the
  parameters can be raised later; ``needs_rehash`` + the login path's
  rehash-on-verify keeps old rows upgrading lazily.

Never log, return, or embed a hash in an error message. The only consumers
are the auth routes and the migration-free ``app_users.password_hash`` column.

Uniform-timing rule: when the presented identifier matches no credentialed
user, callers MUST still run ``verify_password(DUMMY_HASH, ...)`` so unknown
email and wrong password are indistinguishable by response time.
"""

from __future__ import annotations

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

_hasher = PasswordHasher(
    time_cost=3,
    memory_cost=64 * 1024,  # KiB -> 64 MiB
    parallelism=4,
    hash_len=32,
    salt_len=16,
)

# Precomputed at import so the unknown-user login path burns the same argon2
# work as a real verify (anti-enumeration; see module docstring).
DUMMY_HASH = _hasher.hash("deployai-dummy-password-for-uniform-timing")

PASSWORD_MIN_LENGTH = 10
# argon2 has no 72-byte truncation (that's bcrypt), but an unbounded input is
# a hashing-DoS vector; the cap matches the task spec and is far beyond any
# real passphrase.
PASSWORD_MAX_LENGTH = 72

# Small embedded worst-of list (top leaked passwords >= 10 chars, plus obvious
# product-adjacent picks). Deliberately tiny: this blocks the laziest choices
# without composition-rule theater; length is the real policy.
_WORST_PASSWORDS: frozenset[str] = frozenset(
    {
        "1234567890",
        "0123456789",
        "1234567891",
        "12345678910",
        "123456789012",
        "qwertyuiop",
        "qwerty123456",
        "1q2w3e4r5t6y",
        "q1w2e3r4t5y6",
        "abcdefghij",
        "abc12345678",
        "password12",
        "password123",
        "password1234",
        "passw0rd123",
        "password!123",
        "iloveyou123",
        "welcome12345",
        "letmein12345",
        "sunshine123",
        "princess123",
        "football123",
        "baseball123",
        "superman123",
        "trustno1234",
        "dragon123456",
        "monkey123456",
        "master123456",
        "shadow123456",
        "michael123456",
        "jennifer12345",
        "1qaz2wsx3edc",
        "zaq12wsx3edc",
        "aaaaaaaaaa",
        "1111111111",
        "0000000000",
        "asdfghjkl1",
        "changeme123",
        "adminadmin",
        "administrator",
        "deployai123",
    }
)


def hash_password(password: str) -> str:
    """argon2id hash with the pinned parameters above."""
    return _hasher.hash(password)


def verify_password(stored_hash: str, password: str) -> bool:
    """Constant-shape verify: every failure mode is just ``False``."""
    try:
        return _hasher.verify(stored_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def needs_rehash(stored_hash: str) -> bool:
    try:
        return _hasher.check_needs_rehash(stored_hash)
    except InvalidHashError:
        return True


def password_policy_error(password: str) -> str | None:
    """Return a human-readable policy violation, or None when acceptable.

    Policy: length in [10, 72] and not on the embedded worst-passwords list.
    No composition rules on purpose (NIST 800-63B).
    """
    if len(password) < PASSWORD_MIN_LENGTH:
        return f"Password must be at least {PASSWORD_MIN_LENGTH} characters."
    if len(password) > PASSWORD_MAX_LENGTH:
        return f"Password must be at most {PASSWORD_MAX_LENGTH} characters."
    if password.strip().lower() in _WORST_PASSWORDS:
        return "That password is on the most-common-passwords list; pick something less guessable."
    return None
