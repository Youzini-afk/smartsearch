"""Pydantic schemas for the Admin API."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Token
# ---------------------------------------------------------------------------

class TokenCreateRequest(BaseModel):
    name: str = ""
    scopes: dict | None = Field(default_factory=lambda: {"permissions": ["admin"]})
    expires_at: datetime | None = None


class TokenResponse(BaseModel):
    id: str
    name: str
    token_prefix: str
    scopes: dict | None
    is_active: bool
    last_used_at: datetime | None = None
    expires_at: datetime | None = None
    created_at: datetime
    # Only populated on create
    raw_token: str | None = None


# ---------------------------------------------------------------------------
# Provider Credential
# ---------------------------------------------------------------------------

class ProviderCredentialCreateRequest(BaseModel):
    provider: str
    api_key: str
    api_secret: str | None = None
    extra: dict | None = None


class ProviderCredentialResponse(BaseModel):
    id: str
    provider: str
    masked_value: str
    key_fingerprint: str | None = None
    algorithm: str
    key_version: str
    status: str
    is_active: bool
    extra: dict | None = None
    last_used_at: datetime | None = None
    created_at: datetime
    updated_at: datetime | None = None


class ProviderCredentialRevealResponse(BaseModel):
    id: str
    provider: str
    api_key: str
    api_secret: str | None = None


# ---------------------------------------------------------------------------
# Provider Config
# ---------------------------------------------------------------------------

class ProviderConfigCreateRequest(BaseModel):
    provider: str
    capability: str
    is_enabled: bool = True
    priority: int = 0
    settings: dict | None = None


class ProviderConfigResponse(BaseModel):
    id: str
    provider: str
    capability: str
    is_enabled: bool
    priority: int
    settings: dict | None = None
    created_at: datetime
    updated_at: datetime | None = None


# ---------------------------------------------------------------------------
# Summary / Usage / Audit
# ---------------------------------------------------------------------------

class SummaryResponse(BaseModel):
    tokens_total: int = 0
    tokens_active: int = 0
    providers_total: int = 0
    providers_active: int = 0
    invocations_total: int = 0
    invocations_errors: int = 0


class UsageRecord(BaseModel):
    id: str
    tool: str
    provider: str
    is_ok: bool
    error_type: str
    elapsed_ms: int
    created_at: datetime


class AuditRecord(BaseModel):
    id: str
    actor_id: str | None = None
    actor_type: str
    action: str
    target_type: str
    target_id: str
    detail: dict | None = None
    created_at: datetime


class SystemInfoResponse(BaseModel):
    status: str = "ok"
    db_backend: str = "sqlite"
    mcp_mounted: bool = False
    version: str = ""
    dependencies: list[str] = Field(default_factory=list)
