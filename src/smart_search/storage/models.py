"""SQLAlchemy ORM models for cloud foundation."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text, JSON, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Declarative base for all models."""


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _uuid4_str() -> str:
    return str(uuid.uuid4())


# ---------------------------------------------------------------------------
# Tenant / User / Membership
# ---------------------------------------------------------------------------


class Tenant(Base):
    __tablename__ = "tenants"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid4_str)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )

    memberships: Mapped[list[Membership]] = relationship(back_populates="tenant")


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid4_str)
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(128), default="")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    memberships: Mapped[list[Membership]] = relationship(back_populates="user")
    api_tokens: Mapped[list[ApiToken]] = relationship(back_populates="user")


class Membership(Base):
    __tablename__ = "memberships"
    __table_args__ = (UniqueConstraint("tenant_id", "user_id", name="uq_memberships_tenant_user"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid4_str)
    tenant_id: Mapped[str] = mapped_column(String(36), ForeignKey("tenants.id"), nullable=False)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False)
    role: Mapped[str] = mapped_column(String(32), default="member")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    tenant: Mapped[Tenant] = relationship(back_populates="memberships")
    user: Mapped[User] = relationship(back_populates="memberships")


# ---------------------------------------------------------------------------
# Auth tokens
# ---------------------------------------------------------------------------


class ApiToken(Base):
    __tablename__ = "api_tokens"
    __table_args__ = (
        UniqueConstraint("token_hash", name="uq_api_tokens_token_hash"),
        Index("ix_api_tokens_prefix_active", "token_prefix", "is_active"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid4_str)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False)
    tenant_id: Mapped[str] = mapped_column(String(36), ForeignKey("tenants.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(128), default="")
    token_prefix: Mapped[str] = mapped_column(String(32), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    scopes: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    user: Mapped[User] = relationship(back_populates="api_tokens")
    tenant: Mapped[Tenant] = relationship()


# ---------------------------------------------------------------------------
# Provider credentials / configs
# ---------------------------------------------------------------------------


class ProviderCredential(Base):
    __tablename__ = "provider_credentials"
    __table_args__ = (Index("ix_provider_credentials_tenant_provider_active", "tenant_id", "provider", "is_active"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid4_str)
    tenant_id: Mapped[str] = mapped_column(String(36), ForeignKey("tenants.id"), nullable=False)
    provider: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    encrypted_api_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    encrypted_api_secret: Mapped[str | None] = mapped_column(Text, nullable=True)
    key_fingerprint: Mapped[str | None] = mapped_column(String(64), nullable=True)
    masked_value: Mapped[str] = mapped_column(String(128), default="")
    algorithm: Mapped[str] = mapped_column(String(64), default="fernet")
    key_version: Mapped[str] = mapped_column(String(32), default="v1")
    status: Mapped[str] = mapped_column(String(32), default="active")
    extra: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )

    tenant: Mapped[Tenant] = relationship()


class ProviderConfig(Base):
    __tablename__ = "provider_configs"
    __table_args__ = (UniqueConstraint("tenant_id", "provider", "capability", name="uq_provider_configs_tenant_provider_capability"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid4_str)
    tenant_id: Mapped[str] = mapped_column(String(36), ForeignKey("tenants.id"), nullable=False)
    provider: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    capability: Mapped[str] = mapped_column(String(64), nullable=False)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    priority: Mapped[int] = mapped_column(Integer, default=0)
    settings: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )

    tenant: Mapped[Tenant] = relationship()


# ---------------------------------------------------------------------------
# Observability
# ---------------------------------------------------------------------------


class ToolInvocation(Base):
    __tablename__ = "tool_invocations"
    __table_args__ = (Index("ix_tool_invocations_tenant_created", "tenant_id", "created_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid4_str)
    tenant_id: Mapped[str] = mapped_column(String(36), ForeignKey("tenants.id"), nullable=False)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=True)
    token_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    request_id: Mapped[str] = mapped_column(String(36), nullable=False)
    tool: Mapped[str] = mapped_column(String(64), nullable=False)
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    is_ok: Mapped[bool] = mapped_column(Boolean, default=False)
    error_type: Mapped[str] = mapped_column(String(64), default="")
    elapsed_ms: Mapped[int] = mapped_column(Integer, default=0)
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    tenant: Mapped[Tenant] = relationship()


class ProviderUsage(Base):
    __tablename__ = "provider_usage"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid4_str)
    tenant_id: Mapped[str] = mapped_column(String(36), ForeignKey("tenants.id"), nullable=False)
    provider: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    period: Mapped[str] = mapped_column(String(10), nullable=False)  # e.g. "2026-05-18"
    invocation_count: Mapped[int] = mapped_column(Integer, default=0)
    total_elapsed_ms: Mapped[int] = mapped_column(Integer, default=0)
    error_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )

    tenant: Mapped[Tenant] = relationship()


class AuditEvent(Base):
    __tablename__ = "audit_events"
    __table_args__ = (Index("ix_audit_events_tenant_created", "tenant_id", "created_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid4_str)
    tenant_id: Mapped[str] = mapped_column(String(36), ForeignKey("tenants.id"), nullable=False)
    actor_id: Mapped[str] = mapped_column(String(36), nullable=True)
    actor_type: Mapped[str] = mapped_column(String(32), default="user")
    action: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    target_type: Mapped[str] = mapped_column(String(64), default="")
    target_id: Mapped[str] = mapped_column(String(36), default="")
    detail: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    tenant: Mapped[Tenant] = relationship()


# ---------------------------------------------------------------------------
# Task system – TaskRun / TaskNode / TaskAttempt / TaskEvent / TaskArtifact
# ---------------------------------------------------------------------------


class TaskRun(Base):
    """Top-level task (e.g. one Deep Research run)."""
    __tablename__ = "task_runs"
    __table_args__ = (
        Index("ix_task_runs_tenant_status", "tenant_id", "status"),
        Index("ix_task_runs_tenant_created", "tenant_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid4_str)
    tenant_id: Mapped[str] = mapped_column(String(36), ForeignKey("tenants.id"), nullable=False)
    user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    task_type: Mapped[str] = mapped_column(String(64), nullable=False, default="deep_research")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="queued", index=True)
    topic: Mapped[str] = mapped_column(Text, nullable=False, default="")
    params: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )

    tenant: Mapped[Tenant] = relationship()
    nodes: Mapped[list[TaskNode]] = relationship(back_populates="task_run", cascade="all, delete-orphan")


class TaskNode(Base):
    """A single step / node within a task DAG."""
    __tablename__ = "task_nodes"
    __table_args__ = (
        Index("ix_task_nodes_task_run_id", "task_run_id"),
        Index("ix_task_nodes_status", "status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid4_str)
    task_run_id: Mapped[str] = mapped_column(String(36), ForeignKey("task_runs.id"), nullable=False)
    node_type: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    name: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    depends_on: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # list of node ids
    config: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error: Mapped[str] = mapped_column(Text, default="")
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )

    task_run: Mapped[TaskRun] = relationship(back_populates="nodes")
    attempts: Mapped[list[TaskAttempt]] = relationship(back_populates="node", cascade="all, delete-orphan")


class TaskAttempt(Base):
    """Individual attempt of executing a node (retry creates new row)."""
    __tablename__ = "task_attempts"
    __table_args__ = (Index("ix_task_attempts_node_id", "node_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid4_str)
    node_id: Mapped[str] = mapped_column(String(36), ForeignKey("task_nodes.id"), nullable=False)
    attempt_number: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(32), default="running")
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error: Mapped[str] = mapped_column(Text, default="")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    node: Mapped[TaskNode] = relationship(back_populates="attempts")


class TaskEvent(Base):
    """Chronologically appended event log for a task run."""
    __tablename__ = "task_events"
    __table_args__ = (
        Index("ix_task_events_task_run_id", "task_run_id"),
        Index("ix_task_events_created", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid4_str)
    task_run_id: Mapped[str] = mapped_column(String(36), ForeignKey("task_runs.id"), nullable=False)
    node_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False, default="info")
    message: Mapped[str] = mapped_column(Text, default="")
    detail: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class TaskArtifact(Base):
    """Output artifact produced by a task node."""
    __tablename__ = "task_artifacts"
    __table_args__ = (
        Index("ix_task_artifacts_task_run_id", "task_run_id"),
        Index("ix_task_artifacts_node_id", "node_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid4_str)
    task_run_id: Mapped[str] = mapped_column(String(36), ForeignKey("task_runs.id"), nullable=False)
    node_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    artifact_type: Mapped[str] = mapped_column(String(64), nullable=False, default="json")
    name: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    content: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
