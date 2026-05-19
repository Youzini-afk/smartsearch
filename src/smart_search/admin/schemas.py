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


class ProviderConfigUpdateRequest(BaseModel):
    is_enabled: bool | None = None
    priority: int | None = None
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
    # Enhanced fields (opt-in by backend)
    analytics: dict | None = None
    tool_breakdown: dict | None = None
    provider_breakdown: dict | None = None
    trend: list[int] | None = None
    task_summary: dict | None = None
    recent_tasks: list | None = None
    recent_errors: list | None = None


class UsageStatsResponse(BaseModel):
    total_invocations: int = 0
    error_count: int = 0
    avg_latency_ms: int = 0
    by_tool: dict | None = None
    by_provider: dict | None = None


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


# ---------------------------------------------------------------------------
# Analytics / Stats
# ---------------------------------------------------------------------------

class TrendPoint(BaseModel):
    bucket: str = ""
    total: int = 0
    errors: int = 0


class TopError(BaseModel):
    error_type: str = ""
    count: int = 0


class AdminAnalyticsResponse(BaseModel):
    total: int = 0
    errors: int = 0
    success_rate: float = 0.0
    avg_elapsed_ms: int = 0
    by_tool: dict = Field(default_factory=dict)
    by_provider: dict = Field(default_factory=dict)
    top_errors: list[TopError] = Field(default_factory=list)
    trend: list[TrendPoint] = Field(default_factory=list)


class TaskAnalyticsResponse(BaseModel):
    status_counts: dict = Field(default_factory=dict)
    recent_tasks: list[dict] = Field(default_factory=list)


class ProviderGroupResponse(BaseModel):
    provider: str = ""
    credentials: list[dict] = Field(default_factory=list)
    configs: list[dict] = Field(default_factory=list)
    credential_count: int = 0
    config_count: int = 0
    has_active_credential: bool = False
    has_enabled_config: bool = False
