"""Audit logging helpers – thin wrapper around storage.repositories.record_audit_event."""

from __future__ import annotations

from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


_SECRET_KEYWORDS = (
    "authorization",
    "api_key",
    "apikey",
    "api-key",
    "secret",
    "token",
    "password",
    "credential",
    "encrypted",
)


def sanitize_audit_detail(detail: dict | None, *, max_value_length: int = 500) -> dict | None:
    """Return an audit-safe copy with obvious secret fields redacted."""
    if detail is None:
        return None

    def _sanitize(value: Any, path: str = "") -> Any:
        key = path.rsplit(".", 1)[-1].lower()
        if any(word in key for word in _SECRET_KEYWORDS):
            return "[redacted]"
        if isinstance(value, dict):
            return {str(k): _sanitize(v, f"{path}.{k}" if path else str(k)) for k, v in value.items()}
        if isinstance(value, list):
            return [_sanitize(item, path) for item in value[:50]]
        if isinstance(value, str):
            if len(value) > max_value_length:
                return value[:max_value_length] + "…"
            return value
        return value

    return _sanitize(detail)


def log_audit(
    session: Session,
    *,
    tenant_id: str,
    action: str,
    actor_id: str | None = None,
    actor_type: str = "user",
    target_type: str = "",
    target_id: str = "",
    detail: dict | None = None,
) -> None:
    """Record an audit event to the database."""
    from ..storage.repositories import record_audit_event

    record_audit_event(
        session,
        tenant_id=tenant_id,
        action=action,
        actor_id=actor_id,
        actor_type=actor_type,
        target_type=target_type,
        target_id=target_id,
        detail=sanitize_audit_detail(detail),
    )
