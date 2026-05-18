"""API token generation, hashing, and verification.

Token format: ``sk_live_<48 random hex chars>``.
Hash: HMAC-SHA256 with a secret derived from SMART_SEARCH_TOKEN_SECRET
(or the master key as an explicit development fallback).
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import os
import secrets
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from ..storage.models import ApiToken

_logger = logging.getLogger(__name__)

_PREFIX = "sk_live_"


def _token_secret() -> bytes:
    """Return the HMAC secret for token hashing."""
    env = os.getenv("SMART_SEARCH_TOKEN_SECRET")
    if env:
        return env.encode("utf-8")
    master = os.getenv("SMART_SEARCH_MASTER_KEY")
    if master and os.getenv("SMART_SEARCH_ALLOW_INSECURE_DEV_KEYS") == "true":
        return hashlib.sha256(master.encode("utf-8")).digest()
    if os.getenv("SMART_SEARCH_ALLOW_INSECURE_DEV_KEYS") == "true":
        _logger.warning("SMART_SEARCH_TOKEN_SECRET not set; using insecure development token secret")
        return hashlib.sha256(b"smart-search-dev-token-secret").digest()
    raise RuntimeError(
        "SMART_SEARCH_TOKEN_SECRET is required for API token hashing. "
        "Set SMART_SEARCH_ALLOW_INSECURE_DEV_KEYS=true only for local development/tests."
    )


def generate_token() -> str:
    """Generate a new API token string (``sk_live_…``).

    **Never log the return value.**
    """
    random_part = secrets.token_hex(24)  # 48 hex chars
    return f"{_PREFIX}{random_part}"


def token_prefix(token: str) -> str:
    """Return the non-secret lookup prefix stored with a token."""
    if not token.startswith(_PREFIX):
        raise ValueError("invalid smart-search API token prefix")
    return token[: len(_PREFIX) + 12]


def hash_token(token: str) -> str:
    """Return the HMAC-SHA256 hex digest of *token*."""
    return hmac.new(_token_secret(), token.encode("utf-8"), hashlib.sha256).hexdigest()


def verify_token(session: Session, token: str) -> ApiToken | None:
    """Look up the token by prefix + hash and return the matching ApiToken.

    Returns ``None`` if the token is invalid, inactive, or expired.
    """
    from ..storage.models import ApiToken
    from ..storage.repositories import find_api_token_by_prefix
    from datetime import datetime, timezone

    if not token.startswith(_PREFIX):
        return None

    prefix = token_prefix(token)
    candidates = find_api_token_by_prefix(session, prefix)

    expected_hash = hash_token(token)
    now = datetime.now(timezone.utc)

    for candidate in candidates:
        if not hmac.compare_digest(candidate.token_hash, expected_hash):
            continue
        if not candidate.is_active:
            continue
        if candidate.expires_at is not None:
            exp = candidate.expires_at
            # Handle both naive (SQLite) and aware (PostgreSQL) datetimes
            if exp.tzinfo is None:
                exp = exp.replace(tzinfo=timezone.utc)
            if exp < now:
                continue
        # Touch last_used_at
        candidate.last_used_at = now
        session.flush()
        return candidate

    return None
