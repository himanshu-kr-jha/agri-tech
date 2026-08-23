"""Password hashing.

PBKDF2-HMAC-SHA256 from the standard library rather than bcrypt or argon2, for one reason
worth stating: adding a native dependency to a project someone has to `git clone && make
setup` on an unknown machine buys a compiler error more often than it buys security here.
PBKDF2 with a high iteration count is a NIST-approved KDF and is entirely adequate.

If this ever carries real farmer credentials, move to argon2id. The format string below is
versioned precisely so that migration can happen one user at a time on next login.

What this module refuses to do
------------------------------
There is no ``verify_or_none`` that returns the user, no "check if this password looks
right" helper, and no logging of the password argument anywhere. Every function here takes
the password and returns a boolean or a hash, so a caller cannot accidentally end up with a
credential in a log line or an error message.
"""

from __future__ import annotations

import base64
import functools
import hashlib
import hmac
import secrets

#: OWASP's 2023 floor for PBKDF2-HMAC-SHA256 is 600,000. Costs about 0.2 s per login here,
#: which is the point — it is the same 0.2 s for an attacker, per guess.
ITERATIONS = 600_000
ALGORITHM = "pbkdf2_sha256"
SALT_BYTES = 16


def hash_password(password: str, *, iterations: int = ITERATIONS) -> str:
    """Return ``pbkdf2_sha256$iterations$salt$hash``, all base64."""
    if not password:
        raise ValueError("refusing to hash an empty password")
    salt = secrets.token_bytes(SALT_BYTES)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, iterations)
    return "$".join((ALGORITHM, str(iterations), _b64(salt), _b64(digest)))


def verify_password(password: str, stored: str | None) -> bool:
    """Constant-time check. ``False`` for a user with no password set.

    The comparison uses :func:`hmac.compare_digest` rather than ``==``: a byte-by-byte
    comparison leaks how much of the hash matched through timing, and while that is a thin
    channel it costs nothing to close.

    A malformed or unknown-algorithm hash returns ``False`` rather than raising. A stored
    value we cannot parse means nobody can log in as that user, which is the safe direction.
    """
    if not stored or not password:
        return False
    try:
        algorithm, iterations, salt_b64, expected_b64 = stored.split("$")
    except ValueError:
        return False
    if algorithm != ALGORITHM:
        return False
    try:
        salt = _unb64(salt_b64)
        expected = _unb64(expected_b64)
        rounds = int(iterations)
    except (ValueError, TypeError):
        return False
    candidate = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, rounds)
    return hmac.compare_digest(candidate, expected)


@functools.lru_cache(maxsize=1)
def _dummy_hash() -> str:
    """A real hash of a value nobody knows, for burning CPU on a username that does not exist.

    Computed on first use rather than at import: at 600,000 iterations this costs about
    0.2 s, and paying it on every ``import agrivardhak.api.login`` would tax the seed, the
    test collection and every CLI entry point for something only the login path needs.
    """
    return hash_password(secrets.token_urlsafe(32))


def dummy_verify(password: str) -> bool:
    """Do the work of a password check and always return ``False``.

    Call this when the username did not resolve to a user, so both paths cost the same.

    This closes an account-enumeration oracle the login endpoint *claimed* to close in a
    comment while not actually doing it: ``verify_password(pw, None)`` returns False without
    hashing anything, so an unknown username answered in 7 ms against 30 ms for a known one.
    Reading that difference needs no tooling, and on a platform where usernames are farmers'
    names it leaks who is a member.

    Returns a bool rather than nothing so a caller cannot forget to use the result and have
    a future refactor optimise the call away.
    """
    verify_password(password or "x", _dummy_hash())
    return False


def _b64(raw: bytes) -> str:
    return base64.b64encode(raw).decode()


def _unb64(text: str) -> bytes:
    return base64.b64decode(text.encode())
