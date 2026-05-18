"""Repository helpers for common CRUD operations on cloud models."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import (
    ApiToken,
    AuditEvent,
    Membership,
    ProviderConfig,
    ProviderCredential,
    ProviderUsage,
    Tenant,
    ToolInvocation,
    User,
)


# ---------------------------------------------------------------------------
# Tenant
# ---------------------------------------------------------------------------

def create_tenant(session: Session, name: str, slug: str) -> Tenant:
    tenant = Tenant(name=name, slug=slug)
    session.add(tenant)
    session.flush()
    return tenant


def get_tenant_by_slug(session: Session, slug: str) -> Tenant | None:
    return session.execute(select(Tenant).where(Tenant.slug == slug)).scalar_one_or_none()


# ---------------------------------------------------------------------------
# User
# ---------------------------------------------------------------------------

def create_user(session: Session, email: str, display_name: str = "") -> User:
    user = User(email=email, display_name=display_name)
    session.add(user)
    session.flush()
    return user


def get_user_by_email(session: Session, email: str) -> User | None:
    return session.execute(select(User).where(User.email == email)).scalar_one_or_none()


# ---------------------------------------------------------------------------
# Membership
# ---------------------------------------------------------------------------

def add_membership(session: Session, tenant_id: str, user_id: str, role: str = "member") -> Membership:
    m = Membership(tenant_id=tenant_id, user_id=user_id, role=role)
    session.add(m)
    session.flush()
    return m


# ---------------------------------------------------------------------------
# ProviderCredential
# ---------------------------------------------------------------------------

def create_provider_credential(
    session: Session,
    tenant_id: str,
    provider: str,
    *,
    encrypted_api_key: str | None = None,
    encrypted_api_secret: str | None = None,
    key_fingerprint: str | None = None,
    masked_value: str = "",
    algorithm: str = "fernet",
    key_version: str = "v1",
    status: str = "active",
    extra: dict | None = None,
) -> ProviderCredential:
    cred = ProviderCredential(
        tenant_id=tenant_id,
        provider=provider,
        encrypted_api_key=encrypted_api_key,
        encrypted_api_secret=encrypted_api_secret,
        key_fingerprint=key_fingerprint,
        masked_value=masked_value,
        algorithm=algorithm,
        key_version=key_version,
        status=status,
        extra=extra,
    )
    session.add(cred)
    session.flush()
    return cred


def get_active_credentials(session: Session, tenant_id: str, provider: str) -> Sequence[ProviderCredential]:
    stmt = (
        select(ProviderCredential)
        .where(
            ProviderCredential.tenant_id == tenant_id,
            ProviderCredential.provider == provider,
            ProviderCredential.is_active.is_(True),
            ProviderCredential.status == "active",
        )
        .order_by(ProviderCredential.created_at)
    )
    return session.execute(stmt).scalars().all()


# ---------------------------------------------------------------------------
# ProviderConfig
# ---------------------------------------------------------------------------

def create_provider_config(
    session: Session,
    tenant_id: str,
    provider: str,
    capability: str,
    *,
    is_enabled: bool = True,
    priority: int = 0,
    settings: dict | None = None,
) -> ProviderConfig:
    cfg = ProviderConfig(
        tenant_id=tenant_id,
        provider=provider,
        capability=capability,
        is_enabled=is_enabled,
        priority=priority,
        settings=settings,
    )
    session.add(cfg)
    session.flush()
    return cfg


def get_enabled_configs(session: Session, tenant_id: str) -> Sequence[ProviderConfig]:
    stmt = (
        select(ProviderConfig)
        .where(
            ProviderConfig.tenant_id == tenant_id,
            ProviderConfig.is_enabled.is_(True),
        )
        .order_by(ProviderConfig.priority.desc(), ProviderConfig.provider)
    )
    return session.execute(stmt).scalars().all()


# ---------------------------------------------------------------------------
# ApiToken helpers (basic; full token logic in auth/tokens.py)
# ---------------------------------------------------------------------------

def store_api_token(
    session: Session,
    user_id: str,
    tenant_id: str,
    token_prefix: str,
    token_hash: str,
    *,
    name: str = "",
    scopes: dict | None = None,
    expires_at: datetime | None = None,
) -> ApiToken:
    tok = ApiToken(
        user_id=user_id,
        tenant_id=tenant_id,
        name=name,
        token_prefix=token_prefix,
        token_hash=token_hash,
        scopes=scopes,
        expires_at=expires_at,
    )
    session.add(tok)
    session.flush()
    return tok


def find_api_token_by_prefix(session: Session, prefix: str) -> Sequence[ApiToken]:
    stmt = select(ApiToken).where(ApiToken.token_prefix == prefix, ApiToken.is_active.is_(True))
    return session.execute(stmt).scalars().all()


# ---------------------------------------------------------------------------
# Observability
# ---------------------------------------------------------------------------

def record_tool_invocation(
    session: Session,
    *,
    tenant_id: str,
    request_id: str,
    tool: str,
    provider: str,
    is_ok: bool,
    user_id: str | None = None,
    token_id: str | None = None,
    error_type: str = "",
    elapsed_ms: int = 0,
    metadata: dict | None = None,
) -> ToolInvocation:
    inv = ToolInvocation(
        tenant_id=tenant_id,
        user_id=user_id,
        token_id=token_id,
        request_id=request_id,
        tool=tool,
        provider=provider,
        is_ok=is_ok,
        error_type=error_type,
        elapsed_ms=elapsed_ms,
        metadata_=metadata,
    )
    session.add(inv)
    session.flush()
    return inv


def record_audit_event(
    session: Session,
    *,
    tenant_id: str,
    action: str,
    actor_id: str | None = None,
    actor_type: str = "user",
    target_type: str = "",
    target_id: str = "",
    detail: dict | None = None,
) -> AuditEvent:
    from ..security.audit import sanitize_audit_detail

    evt = AuditEvent(
        tenant_id=tenant_id,
        actor_id=actor_id,
        actor_type=actor_type,
        action=action,
        target_type=target_type,
        target_id=target_id,
        detail=sanitize_audit_detail(detail),
    )
    session.add(evt)
    session.flush()
    return evt
