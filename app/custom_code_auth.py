"""Fail-closed credential verification for project-local custom Cost Codes.

Only salted PBKDF2 password hashes are accepted. Plaintext credentials are never
embedded in source, returned by this module, or written to application data.
"""
from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import os
import secrets
from typing import Mapping


USERNAME_ENV = "MURPHY_CUSTOM_CODE_USERNAME"
PASSWORD_HASH_ENV = "MURPHY_CUSTOM_CODE_PASSWORD_HASH"
HASH_NAME = "sha256"
HASH_SCHEME = "pbkdf2_sha256"
DEFAULT_ITERATIONS = 600_000
MINIMUM_ITERATIONS = 210_000
SALT_BYTES = 16


def hash_password(
    password: str, *, iterations: int = DEFAULT_ITERATIONS, salt: bytes | None = None
) -> str:
    """Create a portable salted PBKDF2-HMAC-SHA256 verifier string."""
    if not isinstance(password, str) or not password:
        raise ValueError("A non-empty password is required.")
    if iterations < MINIMUM_ITERATIONS:
        raise ValueError(f"PBKDF2 iterations must be at least {MINIMUM_ITERATIONS}.")
    active_salt = salt if salt is not None else secrets.token_bytes(SALT_BYTES)
    digest = hashlib.pbkdf2_hmac(
        HASH_NAME, password.encode("utf-8"), active_salt, iterations
    )
    salt_text = base64.urlsafe_b64encode(active_salt).decode("ascii").rstrip("=")
    digest_text = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
    return f"{HASH_SCHEME}${iterations}${salt_text}${digest_text}"


def _decode_base64(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


def verify_password(password: str, encoded_hash: str) -> bool:
    """Verify one password without exposing parser or comparison details."""
    try:
        scheme, raw_iterations, raw_salt, raw_digest = encoded_hash.split("$", 3)
        iterations = int(raw_iterations)
        if scheme != HASH_SCHEME or iterations < MINIMUM_ITERATIONS:
            return False
        salt = _decode_base64(raw_salt)
        expected = _decode_base64(raw_digest)
        candidate = hashlib.pbkdf2_hmac(
            HASH_NAME, str(password).encode("utf-8"), salt, iterations,
            dklen=len(expected),
        )
        return hmac.compare_digest(candidate, expected)
    except (AttributeError, TypeError, ValueError, binascii.Error):
        return False


def _load_credentials(
    environment: Mapping[str, str],
    stored_credentials: Mapping[str, str] | None = None,
) -> tuple[str, str] | None:
    username = environment.get(USERNAME_ENV)
    password_hash = environment.get(PASSWORD_HASH_ENV)
    if username and password_hash:
        return username, password_hash

    if stored_credentials:
        stored_username = stored_credentials.get("username")
        stored_hash = stored_credentials.get("password_hash")
        if isinstance(stored_username, str) and isinstance(stored_hash, str):
            return stored_username, stored_hash

    return None


def verify_custom_code_credentials(
    username: str,
    password: str,
    *,
    environment: Mapping[str, str] | None = None,
    stored_credentials: Mapping[str, str] | None = None,
) -> bool:
    """Return only whether the dedicated custom-code credential is valid.

    Missing, partial, malformed, or weak configuration always fails closed. The
    caller should emit a generic authorization error and must not include either
    submitted value in logs, audit records, or responses.
    """
    configured = _load_credentials(environment or os.environ, stored_credentials)
    if configured is None:
        return False
    expected_username, encoded_hash = configured
    supplied_username = username if isinstance(username, str) else ""
    username_matches = hmac.compare_digest(
        hashlib.sha256(supplied_username.encode("utf-8")).digest(),
        hashlib.sha256(expected_username.encode("utf-8")).digest(),
    )
    # Always perform the expensive password check even when the username is
    # wrong, avoiding an obvious timing distinction at this small boundary.
    password_matches = verify_password(password if isinstance(password, str) else "", encoded_hash)
    return bool(username_matches & password_matches)
