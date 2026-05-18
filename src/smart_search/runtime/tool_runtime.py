"""ToolRuntime – thin async wrapper for cloud-mode tool calls.

Phase 1 delegates to existing ``service`` functions.
Phase 2 will add proper provider orchestration, metering, etc.
"""

from __future__ import annotations

from typing import Any

from .context import ToolContext
from .config_resolver import LocalConfigResolver, CloudConfigResolver, ResolvedToolConfig


class ToolRuntime:
    """Runtime façade for local/cloud tool calls.

    Phase 1 resolves cloud configuration and carries it on ``ctx`` for server
    adapters. Existing service functions still use local/global config until
    Phase 2 adds provider-injection seams.
    """

    def __init__(self, ctx: ToolContext, resolved_configs: list[ResolvedToolConfig] | None = None) -> None:
        self.ctx = ctx
        self._configs = resolved_configs

    @classmethod
    def from_local(cls, ctx: ToolContext) -> ToolRuntime:
        """Build a runtime using the local CLI config resolver."""
        resolver = LocalConfigResolver()
        configs = resolver.resolve()
        return cls(ctx=ctx, resolved_configs=configs)

    @classmethod
    def from_cloud(cls, ctx: ToolContext, session: Any) -> ToolRuntime:
        """Build a runtime using the cloud DB config resolver."""
        resolver = CloudConfigResolver(session=session, tenant_id=ctx.tenant_id)
        configs = resolver.resolve()
        ctx.provider_config = configs
        return cls(ctx=ctx, resolved_configs=configs)

    # ------------------------------------------------------------------
    # Public API – thin wrappers over service functions
    # ------------------------------------------------------------------

    async def search(self, query: str, **kwargs: Any) -> dict[str, Any]:
        """Run a search, delegating to ``service.search``."""
        from ..service import search as _search

        return await _search(query, **kwargs)

    async def fetch(self, url: str, **kwargs: Any) -> dict[str, Any]:
        """Fetch a URL, delegating to ``service.fetch``."""
        from ..service import fetch as _fetch

        return await _fetch(url, **kwargs)

    def deep_plan(self, query: str, **kwargs: Any) -> dict[str, Any]:
        """Generate a deep research plan, delegating to ``service.build_deep_research_plan``."""
        from ..service import build_deep_research_plan as _plan

        return _plan(query, **kwargs)

    async def doctor(self, **kwargs: Any) -> dict[str, Any]:
        """Run doctor diagnostics, delegating to ``service.doctor``."""
        from ..service import doctor as _doctor

        return await _doctor(**kwargs)
