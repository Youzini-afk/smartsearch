"""Request-scoped context for cloud tool calls."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ToolContext:
    """Carries identity and config for a single tool invocation.

    Constructed by the cloud gateway after authentication, consumed by
    ToolRuntime and provider factory.
    """

    request_id: str
    tenant_id: str
    user_id: str | None
    token_id: str | None
    scopes: list[str] = field(default_factory=list)
    provider_config: Any = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
