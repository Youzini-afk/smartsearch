"""Reversible encryption for provider keys/secrets.

Uses cryptography.fernet.MultiFernet for key rotation support.
Master key comes from SMART_SEARCH_MASTER_KEY (or explicit arg).
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import os
import warnings

from cryptography.fernet import Fernet, MultiFernet, InvalidToken

_logger = logging.getLogger(__name__)

_master_fernet: MultiFernet | None = None
_master_key_warning_emitted = False


def _derive_fernet_key(raw: str) -> bytes:
    """Derive a 32-byte Fernet key from arbitrary input via SHA-256.

    Accepts either a proper URL-safe base64 Fernet key or an arbitrary
    secret string that gets hashed to 32 bytes.
    """
    raw = raw.strip()
    # Try as a proper Fernet key first
    try:
        decoded = base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4))
        if len(decoded) == 32:
            return base64.urlsafe_b64encode(decoded)
    except Exception:
        pass
    # Fallback: hash the raw string to produce a valid Fernet key
    digest = hashlib.sha256(raw.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest)


def _get_master_fernet(explicit_key: str | None = None) -> MultiFernet:
    """Lazily initialise the global MultiFernet instance."""
    global _master_fernet, _master_key_warning_emitted

    if explicit_key is not None:
        key = _derive_fernet_key(explicit_key)
        return MultiFernet([Fernet(key)])

    if _master_fernet is not None:
        return _master_fernet

    env_key = os.getenv("SMART_SEARCH_MASTER_KEY")
    if env_key:
        # Support comma-separated keys for rotation (first = primary)
        parts = [p.strip() for p in env_key.split(",") if p.strip()]
        fernets = [Fernet(_derive_fernet_key(p)) for p in parts]
        _master_fernet = MultiFernet(fernets)
    else:
        if os.getenv("SMART_SEARCH_ALLOW_INSECURE_DEV_KEYS") != "true":
            raise RuntimeError(
                "SMART_SEARCH_MASTER_KEY is required for secret encryption. "
                "Set SMART_SEARCH_ALLOW_INSECURE_DEV_KEYS=true only for local development/tests."
            )
        if not _master_key_warning_emitted:
            _master_key_warning_emitted = True
            warnings.warn(
                "SMART_SEARCH_MASTER_KEY not set – using ephemeral key. "
                "Encrypted values will not survive process restart. "
                "Set SMART_SEARCH_MASTER_KEY in production.",
                stacklevel=2,
            )
            _logger.warning(
                "SMART_SEARCH_MASTER_KEY not set – using ephemeral key. "
                "Encrypted values will not survive process restart."
            )
        # Ephemeral key for dev/test
        ephemeral = Fernet(Fernet.generate_key())
        _master_fernet = MultiFernet([ephemeral])

    return _master_fernet


def reset_master_fernet() -> None:
    """Reset the cached fernet (useful in tests)."""
    global _master_fernet, _master_key_warning_emitted
    _master_fernet = None
    _master_key_warning_emitted = False


def encrypt_secret(plaintext: str, *, key: str | None = None) -> str:
    """Encrypt a secret string, returning a base64 token."""
    f = _get_master_fernet(explicit_key=key)
    return f.encrypt(plaintext.encode("utf-8")).decode("ascii")


def decrypt_secret(token: str, *, key: str | None = None) -> str:
    """Decrypt a token back to the original secret."""
    f = _get_master_fernet(explicit_key=key)
    return f.decrypt(token.encode("ascii")).decode("utf-8")


def mask_secret(secret: str, visible: int = 4) -> str:
    """Return a masked representation, e.g. 'sk_l…3f9x'."""
    if not secret:
        return "***"
    if len(secret) <= visible * 2:
        return "***"
    return f"{secret[:visible]}…{secret[-visible:]}"


def fingerprint_secret(secret: str) -> str:
    """Return a stable keyed fingerprint for comparison without revealing the secret."""
    key = os.getenv("SMART_SEARCH_FINGERPRINT_SECRET") or os.getenv("SMART_SEARCH_TOKEN_SECRET") or os.getenv("SMART_SEARCH_MASTER_KEY")
    if not key:
        if os.getenv("SMART_SEARCH_ALLOW_INSECURE_DEV_KEYS") != "true":
            raise RuntimeError(
                "SMART_SEARCH_FINGERPRINT_SECRET, SMART_SEARCH_TOKEN_SECRET, or SMART_SEARCH_MASTER_KEY is required"
            )
        key = "smart-search-dev-fingerprint-secret"
    return hmac.new(key.encode("utf-8"), secret.encode("utf-8"), hashlib.sha256).hexdigest()[:24]
