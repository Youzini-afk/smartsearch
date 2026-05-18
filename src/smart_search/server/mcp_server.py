"""MCP server – registers smart-search tools via the official MCP Python SDK.

If the ``mcp`` package is not installed, ``create_mcp_server`` returns
``None`` and the rest of the application continues to work normally.
The import is wrapped so that missing ``mcp`` never crashes the app.
"""

from __future__ import annotations

import hashlib
import time
from typing import Any

from .tools import (
    _input_hash,
    _input_preview,
    _safe_metadata,
    record_usage,
)
from ..runtime.context import ToolContext


def create_mcp_server(session_factory: Any) -> Any | None:
    """Create a FastMCP server with all smart-search tools registered.

    Returns ``None`` if the ``mcp`` package is not installed.
    """
    try:
        from mcp.server.fastmcp import FastMCP
    except ImportError:
        return None

    mcp = FastMCP("smart-search")

    # ---- Helper to build a ToolContext from MCP auth ----------------------

    def _make_ctx() -> ToolContext:
        """Build a minimal ToolContext for MCP tool calls.

        In production, the MCP transport would carry auth info.
        For now, we build a default context that can be overridden
        once MCP auth is fully integrated.
        """
        import uuid

        return ToolContext(
            request_id=str(uuid.uuid4()),
            tenant_id="mcp-default",
            user_id=None,
            token_id=None,
            scopes=["search:read"],
        )

    def _get_session() -> Any:
        return session_factory()

    # ---- Register tools ----------------------------------------------------

    @mcp.tool()
    async def search(
        query: str,
        platform: str = "",
        model: str = "",
        extra_sources: int = 0,
        validation: str = "",
        fallback: str = "",
        providers: str = "auto",
    ) -> dict[str, Any]:
        """Search the web and return an AI-generated answer with sources."""
        from ..service import search as _search

        ctx = _make_ctx()
        session = _get_session()
        start = time.time()
        preview = _input_preview(query)
        ihash = _input_hash(query)
        try:
            result = await _search(
                query,
                platform=platform,
                model=model,
                extra_sources=extra_sources,
                validation=validation,
                fallback=fallback,
                providers=providers,
            )
            elapsed = int((time.time() - start) * 1000)
            p = result.get("providers_used", ["unknown"])
            record_usage(
                session, ctx=ctx, tool="search", provider=p[0] if p else "unknown",
                is_ok=result.get("ok", False), elapsed_ms=elapsed,
                error_type=result.get("error_type", ""),
                input_preview=preview, input_hash_val=ihash,
                extra_meta=_safe_metadata(result),
            )
            session.commit()
            return result
        except Exception:
            elapsed = int((time.time() - start) * 1000)
            record_usage(
                session, ctx=ctx, tool="search", provider="unknown",
                is_ok=False, elapsed_ms=elapsed, error_type="runtime_error",
                input_preview=preview, input_hash_val=ihash,
            )
            session.rollback()
            raise
        finally:
            session.close()

    @mcp.tool()
    async def fetch_url(url: str) -> dict[str, Any]:
        """Fetch and extract content from a URL."""
        from ..service import fetch as _fetch

        ctx = _make_ctx()
        session = _get_session()
        start = time.time()
        preview = _input_preview(url)
        ihash = _input_hash(url)
        try:
            result = await _fetch(url)
            elapsed = int((time.time() - start) * 1000)
            record_usage(
                session, ctx=ctx, tool="fetch_url", provider=result.get("provider", "unknown"),
                is_ok=result.get("ok", False), elapsed_ms=elapsed,
                error_type=result.get("error_type", ""),
                input_preview=preview, input_hash_val=ihash,
                extra_meta=_safe_metadata(result),
            )
            session.commit()
            return result
        except Exception:
            elapsed = int((time.time() - start) * 1000)
            record_usage(
                session, ctx=ctx, tool="fetch_url", provider="unknown",
                is_ok=False, elapsed_ms=elapsed, error_type="runtime_error",
                input_preview=preview, input_hash_val=ihash,
            )
            session.rollback()
            raise
        finally:
            session.close()

    @mcp.tool()
    async def map_site(
        url: str,
        instructions: str = "",
        max_depth: int = 1,
        max_breadth: int = 20,
        limit: int = 50,
        timeout: int = 150,
    ) -> dict[str, Any]:
        """Map a website's structure and URLs."""
        from ..service import map_site as _map_site

        ctx = _make_ctx()
        session = _get_session()
        start = time.time()
        preview = _input_preview(url)
        ihash = _input_hash(url)
        try:
            result = await _map_site(url, instructions, max_depth, max_breadth, limit, timeout)
            elapsed = int((time.time() - start) * 1000)
            record_usage(
                session, ctx=ctx, tool="map_site", provider="tavily",
                is_ok=result.get("ok", False), elapsed_ms=elapsed,
                error_type=result.get("error_type", ""),
                input_preview=preview, input_hash_val=ihash,
                extra_meta=_safe_metadata(result),
            )
            session.commit()
            return result
        except Exception:
            elapsed = int((time.time() - start) * 1000)
            record_usage(
                session, ctx=ctx, tool="map_site", provider="tavily",
                is_ok=False, elapsed_ms=elapsed, error_type="runtime_error",
                input_preview=preview, input_hash_val=ihash,
            )
            session.rollback()
            raise
        finally:
            session.close()

    @mcp.tool()
    async def docs_search(
        query: str,
        library_id: str = "",
        name: str = "",
    ) -> dict[str, Any]:
        """Search documentation via Context7. If library_id is given, fetch docs; otherwise search libraries."""
        ctx = _make_ctx()
        session = _get_session()
        start = time.time()
        preview = _input_preview(query)
        ihash = _input_hash(query)
        try:
            if library_id:
                from ..service import context7_docs as _docs

                result = await _docs(library_id, query)
                provider_used = "context7-docs"
            else:
                from ..service import context7_library as _library

                result = await _library(name or query, query)
                provider_used = "context7-library"

            elapsed = int((time.time() - start) * 1000)
            record_usage(
                session, ctx=ctx, tool="docs_search", provider=provider_used,
                is_ok=result.get("ok", False), elapsed_ms=elapsed,
                error_type=result.get("error_type", ""),
                input_preview=preview, input_hash_val=ihash,
                extra_meta=_safe_metadata(result),
            )
            session.commit()
            return result
        except Exception:
            elapsed = int((time.time() - start) * 1000)
            record_usage(
                session, ctx=ctx, tool="docs_search", provider="context7",
                is_ok=False, elapsed_ms=elapsed, error_type="runtime_error",
                input_preview=preview, input_hash_val=ihash,
            )
            session.rollback()
            raise
        finally:
            session.close()

    @mcp.tool()
    async def web_search(
        query: str,
        count: int = 10,
        provider: str = "auto",
    ) -> dict[str, Any]:
        """Search the web via Exa or Zhipu. Provider: auto/exa/zhipu."""
        ctx = _make_ctx()
        session = _get_session()
        start = time.time()
        preview = _input_preview(query)
        ihash = _input_hash(query)
        try:
            provider_lower = (provider or "auto").strip().lower()

            if provider_lower in ("zhipu",) or (provider_lower == "auto"):
                try:
                    from ..service import zhipu_search as _zhipu

                    result = await _zhipu(query, count=count)
                    if result.get("ok") or provider_lower == "zhipu":
                        provider_used = "zhipu"
                    else:
                        from ..service import exa_search as _exa

                        result = await _exa(query, num_results=count)
                        provider_used = "exa"
                except Exception:
                    if provider_lower == "auto":
                        from ..service import exa_search as _exa

                        result = await _exa(query, num_results=count)
                        provider_used = "exa"
                    else:
                        raise
            elif provider_lower in ("exa",):
                from ..service import exa_search as _exa

                result = await _exa(query, num_results=count)
                provider_used = "exa"
            else:
                return {
                    "ok": False,
                    "error_type": "parameter_error",
                    "error": f"Unknown web_search provider: {provider}",
                }

            elapsed = int((time.time() - start) * 1000)
            record_usage(
                session, ctx=ctx, tool="web_search", provider=provider_used,
                is_ok=result.get("ok", False), elapsed_ms=elapsed,
                error_type=result.get("error_type", ""),
                input_preview=preview, input_hash_val=ihash,
                extra_meta=_safe_metadata(result),
            )
            session.commit()
            return result
        except Exception:
            elapsed = int((time.time() - start) * 1000)
            record_usage(
                session, ctx=ctx, tool="web_search", provider="unknown",
                is_ok=False, elapsed_ms=elapsed, error_type="runtime_error",
                input_preview=preview, input_hash_val=ihash,
            )
            session.rollback()
            raise
        finally:
            session.close()

    @mcp.tool()
    def deep_plan(
        query: str,
        budget: str = "standard",
        evidence_dir: str = "",
    ) -> dict[str, Any]:
        """Generate a deep research plan with sub-questions and steps."""
        from ..service import build_deep_research_plan as _plan

        ctx = _make_ctx()
        session = _get_session()
        start = time.time()
        preview = _input_preview(query)
        ihash = _input_hash(query)
        try:
            result = _plan(query, budget=budget, evidence_dir=evidence_dir)
            elapsed = int((time.time() - start) * 1000)
            record_usage(
                session, ctx=ctx, tool="deep_plan", provider="planner",
                is_ok=result.get("ok", False), elapsed_ms=elapsed,
                error_type=result.get("error_type", ""),
                input_preview=preview, input_hash_val=ihash,
                extra_meta=_safe_metadata(result),
            )
            session.commit()
            return result
        except Exception:
            elapsed = int((time.time() - start) * 1000)
            record_usage(
                session, ctx=ctx, tool="deep_plan", provider="planner",
                is_ok=False, elapsed_ms=elapsed, error_type="runtime_error",
                input_preview=preview, input_hash_val=ihash,
            )
            session.rollback()
            raise
        finally:
            session.close()

    @mcp.tool()
    async def doctor() -> dict[str, Any]:
        """Run diagnostic checks on all configured providers."""
        from ..service import doctor as _doctor

        ctx = _make_ctx()
        session = _get_session()
        start = time.time()
        try:
            result = await _doctor()
            elapsed = int((time.time() - start) * 1000)
            record_usage(
                session, ctx=ctx, tool="doctor", provider="diagnostic",
                is_ok=result.get("ok", False), elapsed_ms=elapsed,
                error_type=result.get("error_type", ""),
            )
            session.commit()
            return result
        except Exception:
            elapsed = int((time.time() - start) * 1000)
            record_usage(
                session, ctx=ctx, tool="doctor", provider="diagnostic",
                is_ok=False, elapsed_ms=elapsed, error_type="runtime_error",
            )
            session.rollback()
            raise
        finally:
            session.close()

    # Return the ASGI app from FastMCP
    try:
        return mcp.streamable_http_app()
    except AttributeError:
        try:
            return mcp.get_app()
        except AttributeError:
            return mcp
