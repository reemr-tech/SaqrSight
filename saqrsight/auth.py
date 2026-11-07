"""Local user accounts: password hashing, sessions and simple login throttling.

Passwords are never stored. Each is hashed with PBKDF2-HMAC-SHA256 (Python standard library),
a random 16-byte salt per user and 310,000 iterations, stored as
    pbkdf2_sha256$<iterations>$<salt hex>$<hash hex>
Sessions are random 256-bit tokens kept in an HttpOnly cookie; only a SHA-256 hash of the token is
stored in the database, so a copy of the database cannot be used to log in.
"""
from __future__ import annotations

import hashlib
import hmac
import re
import secrets
import threading
import time

ITERATIONS = 310_000
SESSION_COOKIE = "saqr_session"
SESSION_DAYS = 14
MIN_PASSWORD = 8
EMAIL_RE = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,190}\.[^@\s]{2,}$")


def hash_password(password: str, iterations: int = ITERATIONS) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return f"pbkdf2_sha256${iterations}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, iters, salt_hex, hash_hex = stored.split("$")
        if algo != "pbkdf2_sha256":
            return False
        digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), int(iters))
        return hmac.compare_digest(digest.hex(), hash_hex)
    except (ValueError, TypeError):
        return False


def new_token() -> str:
    return secrets.token_urlsafe(32)


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def normalize_email(email: str) -> str:
    return (email or "").strip().lower()


def validate_signup(name: str, email: str, password: str) -> str | None:
    """Return an error message, or None if the details are acceptable."""
    if not (name or "").strip() or len(name.strip()) > 80:
        return "Enter your name (up to 80 characters)."
    if not EMAIL_RE.match(normalize_email(email)):
        return "Enter a valid email address."
    if len(password or "") < MIN_PASSWORD:
        return f"Use a password of at least {MIN_PASSWORD} characters."
    if len(password) > 256:
        return "Password is too long."
    return None


class Throttle:
    """After 5 failed logins for an email within 10 minutes, refuse further attempts for 5 minutes."""

    def __init__(self, limit: int = 5, window: float = 600, lock: float = 300):
        self.limit, self.window, self.lock = limit, window, lock
        self._fails: dict[str, list[float]] = {}
        self._mutex = threading.Lock()

    def blocked(self, key: str) -> bool:
        now = time.monotonic()
        with self._mutex:
            fails = [t for t in self._fails.get(key, []) if now - t < self.window]
            self._fails[key] = fails
            return len(fails) >= self.limit and now - fails[-1] < self.lock

    def fail(self, key: str) -> None:
        with self._mutex:
            self._fails.setdefault(key, []).append(time.monotonic())

    def reset(self, key: str) -> None:
        with self._mutex:
            self._fails.pop(key, None)
