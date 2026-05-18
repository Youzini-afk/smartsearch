"""Masking utilities for safe display of secrets."""

from __future__ import annotations


def mask_api_key(key: str | None, visible: int = 4) -> str:
    """Mask an API key for safe display, e.g. 'sk_l…3f9x'."""
    if not key:
        return "未配置"
    if len(key) <= visible * 2:
        return "***"
    return f"{key[:visible]}{'*' * (len(key) - visible * 2)}{key[-visible:]}"


def mask_token(token: str | None, visible: int = 4) -> str:
    """Mask a bearer token.  Never logs the raw value."""
    if not token:
        return "***"
    if len(token) <= visible * 2:
        return "***"
    return f"{token[:visible]}…{token[-visible:]}"
