"""Unified tool dispatcher – maps tool names to service functions.

Each tool invocation is wrapped with usage recording (tool_invocations)
and audit logging (audit_events). The dispatcher never logs full
Authorization headers or provider API keys; only input_preview (first
100 chars) and input_hash are stored in metadata.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import os
import time
from typing import Any

from ..runtime.context import ToolContext

_logger = logging.getLogger(__name__)


def _input_preview(value: str, max_len: int = 100) -> str:
    """Return first *max_len* chars of *value* for safe storage."""
    if os.getenv("SMART_SEARCH_AUDIT_INPUT_PREVIEW", "preview").lower() in {"off", "hash_only", "none"}:
        return ""
    if not value:
        return ""
    return value[:max_len]


def _input_hash(value: str) -> str:
    """Keyed HMAC digest of *value* for dedup / integrity check."""
    key = (
        os.getenv("SMART_SEARCH_AUDIT_HASH_SECRET")
        or os.getenv("SMART_SEARCH_TOKEN_SECRET")
        or os.getenv("SMART_SEARCH_MASTER_KEY")
        or "smart-search-dev-audit-hash-secret"
    )
    return hmac.new(key.encode("utf-8"), value.encode("utf-8", errors="replace"), hashlib.sha256).hexdigest()


def _safe_metadata(result: dict[str, Any]) -> dict[str, Any]:
    """Extract safe fields from a result dict for usage metadata.

    Never includes full API keys, Authorization headers, or complete
    user queries.
    """
    meta: dict[str, Any] = {}
    providers_used = result.get("providers_used", [])
    if providers_used:
        meta["providers_used"] = providers_used
    source_count = result.get("sources_count", 0)
    if source_count:
        meta["source_count"] = source_count
    provider = result.get("provider", "")
    if provider:
        meta["provider"] = provider
    error_type = result.get("error_type", "")
    if error_type:
        meta["error_type"] = error_type
    return meta


def record_usage(
    session: Any,
    *,
    ctx: ToolContext,
    tool: str,
    provider: str,
    is_ok: bool,
    elapsed_ms: int,
    error_type: str = "",
    input_preview: str = "",
    input_hash_val: str = "",
    extra_meta: dict[str, Any] | None = None,
) -> None:
    """Write a tool_invocations row and an audit event."""
    from ..storage.repositories import record_tool_invocation
    from ..security.audit import log_audit

    meta: dict[str, Any] = {"input_preview": input_preview, "input_hash": input_hash_val}
    if extra_meta:
        meta.update(extra_meta)

    try:
        record_tool_invocation(
            session,
            tenant_id=ctx.tenant_id,
            request_id=ctx.request_id,
            tool=tool,
            provider=provider,
            is_ok=is_ok,
            user_id=ctx.user_id,
            token_id=ctx.token_id,
            error_type=error_type,
            elapsed_ms=elapsed_ms,
            metadata=meta,
        )
    except Exception as exc:
        _logger.warning("Failed to record tool usage for request %s: %s", ctx.request_id, type(exc).__name__)

    try:
        log_audit(
            session,
            tenant_id=ctx.tenant_id,
            action="tool.invoke",
            actor_id=ctx.user_id,
            actor_type="api_token",
            target_type="tool",
            target_id=tool,
            detail={
                "tool": tool,
                "provider": provider,
                "is_ok": is_ok,
                "error_type": error_type,
                "elapsed_ms": elapsed_ms,
                "input_preview": input_preview,
            },
        )
    except Exception as exc:
        _logger.warning("Failed to record audit event for request %s: %s", ctx.request_id, type(exc).__name__)


async def dispatch_search(
    ctx: ToolContext,
    session: Any,
    query: str,
    platform: str = "",
    model: str = "",
    extra_sources: int = 0,
    validation: str = "",
    fallback: str = "",
    providers: str = "auto",
) -> dict[str, Any]:
    """Dispatch search tool."""
    from ..service import search as _search

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
        provider = result.get("providers_used", ["unknown"])
        provider_name = provider[0] if provider else "unknown"
        is_ok = result.get("ok", False)

        record_usage(
            session,
            ctx=ctx,
            tool="search",
            provider=provider_name,
            is_ok=is_ok,
            elapsed_ms=elapsed,
            error_type=result.get("error_type", ""),
            input_preview=preview,
            input_hash_val=ihash,
            extra_meta=_safe_metadata(result),
        )
        return result
    except Exception as exc:
        elapsed = int((time.time() - start) * 1000)
        record_usage(
            session,
            ctx=ctx,
            tool="search",
            provider="unknown",
            is_ok=False,
            elapsed_ms=elapsed,
            error_type="runtime_error",
            input_preview=preview,
            input_hash_val=ihash,
        )
        raise


async def dispatch_fetch_url(
    ctx: ToolContext,
    session: Any,
    url: str,
) -> dict[str, Any]:
    """Dispatch fetch_url tool."""
    from ..service import fetch as _fetch

    start = time.time()
    preview = _input_preview(url)
    ihash = _input_hash(url)
    try:
        result = await _fetch(url)
        elapsed = int((time.time() - start) * 1000)
        provider = result.get("provider", "unknown")
        is_ok = result.get("ok", False)

        record_usage(
            session,
            ctx=ctx,
            tool="fetch_url",
            provider=provider,
            is_ok=is_ok,
            elapsed_ms=elapsed,
            error_type=result.get("error_type", ""),
            input_preview=preview,
            input_hash_val=ihash,
            extra_meta=_safe_metadata(result),
        )
        return result
    except Exception as exc:
        elapsed = int((time.time() - start) * 1000)
        record_usage(
            session,
            ctx=ctx,
            tool="fetch_url",
            provider="unknown",
            is_ok=False,
            elapsed_ms=elapsed,
            error_type="runtime_error",
            input_preview=preview,
            input_hash_val=ihash,
        )
        raise


async def dispatch_map_site(
    ctx: ToolContext,
    session: Any,
    url: str,
    instructions: str = "",
    max_depth: int = 1,
    max_breadth: int = 20,
    limit: int = 50,
    timeout: int = 150,
) -> dict[str, Any]:
    """Dispatch map_site tool."""
    from ..service import map_site as _map_site

    start = time.time()
    preview = _input_preview(url)
    ihash = _input_hash(url)
    try:
        result = await _map_site(url, instructions, max_depth, max_breadth, limit, timeout)
        elapsed = int((time.time() - start) * 1000)
        provider = "tavily"
        is_ok = result.get("ok", False)

        record_usage(
            session,
            ctx=ctx,
            tool="map_site",
            provider=provider,
            is_ok=is_ok,
            elapsed_ms=elapsed,
            error_type=result.get("error_type", ""),
            input_preview=preview,
            input_hash_val=ihash,
            extra_meta=_safe_metadata(result),
        )
        return result
    except Exception as exc:
        elapsed = int((time.time() - start) * 1000)
        record_usage(
            session,
            ctx=ctx,
            tool="map_site",
            provider="tavily",
            is_ok=False,
            elapsed_ms=elapsed,
            error_type="runtime_error",
            input_preview=preview,
            input_hash_val=ihash,
        )
        raise


async def dispatch_docs_search(
    ctx: ToolContext,
    session: Any,
    query: str,
    library_id: str = "",
    name: str = "",
) -> dict[str, Any]:
    """Dispatch docs_search tool.

    If *library_id* is provided, call context7_docs; otherwise call
    context7_library (optionally with *name*).
    """
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
        is_ok = result.get("ok", False)

        record_usage(
            session,
            ctx=ctx,
            tool="docs_search",
            provider=provider_used,
            is_ok=is_ok,
            elapsed_ms=elapsed,
            error_type=result.get("error_type", ""),
            input_preview=preview,
            input_hash_val=ihash,
            extra_meta=_safe_metadata(result),
        )
        return result
    except Exception as exc:
        elapsed = int((time.time() - start) * 1000)
        record_usage(
            session,
            ctx=ctx,
            tool="docs_search",
            provider="context7",
            is_ok=False,
            elapsed_ms=elapsed,
            error_type="runtime_error",
            input_preview=preview,
            input_hash_val=ihash,
        )
        raise


async def dispatch_web_search(
    ctx: ToolContext,
    session: Any,
    query: str,
    count: int = 10,
    provider: str = "auto",
) -> dict[str, Any]:
    """Dispatch web_search tool.

    Routes to exa_search or zhipu_search based on *provider* param.
    ``auto`` tries zhipu first (better for Chinese queries), then exa.
    """
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
                    # Fallback to exa if auto
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
        is_ok = result.get("ok", False)

        record_usage(
            session,
            ctx=ctx,
            tool="web_search",
            provider=provider_used,
            is_ok=is_ok,
            elapsed_ms=elapsed,
            error_type=result.get("error_type", ""),
            input_preview=preview,
            input_hash_val=ihash,
            extra_meta=_safe_metadata(result),
        )
        return result
    except Exception as exc:
        elapsed = int((time.time() - start) * 1000)
        record_usage(
            session,
            ctx=ctx,
            tool="web_search",
            provider="unknown",
            is_ok=False,
            elapsed_ms=elapsed,
            error_type="runtime_error",
            input_preview=preview,
            input_hash_val=ihash,
        )
        raise


def dispatch_deep_plan(
    ctx: ToolContext,
    session: Any,
    query: str,
    budget: str = "standard",
    evidence_dir: str = "",
) -> dict[str, Any]:
    """Dispatch deep_plan tool (synchronous)."""
    from ..service import build_deep_research_plan as _plan

    start = time.time()
    preview = _input_preview(query)
    ihash = _input_hash(query)

    try:
        result = _plan(query, budget=budget, evidence_dir=evidence_dir)
        elapsed = int((time.time() - start) * 1000)
        is_ok = result.get("ok", False)

        record_usage(
            session,
            ctx=ctx,
            tool="deep_plan",
            provider="planner",
            is_ok=is_ok,
            elapsed_ms=elapsed,
            error_type=result.get("error_type", ""),
            input_preview=preview,
            input_hash_val=ihash,
            extra_meta=_safe_metadata(result),
        )
        return result
    except Exception as exc:
        elapsed = int((time.time() - start) * 1000)
        record_usage(
            session,
            ctx=ctx,
            tool="deep_plan",
            provider="planner",
            is_ok=False,
            elapsed_ms=elapsed,
            error_type="runtime_error",
            input_preview=preview,
            input_hash_val=ihash,
        )
        raise


async def dispatch_doctor(
    ctx: ToolContext,
    session: Any,
) -> dict[str, Any]:
    """Dispatch doctor tool."""
    from ..service import doctor as _doctor

    start = time.time()
    try:
        result = await _doctor()
        elapsed = int((time.time() - start) * 1000)
        is_ok = result.get("ok", False)

        record_usage(
            session,
            ctx=ctx,
            tool="doctor",
            provider="diagnostic",
            is_ok=is_ok,
            elapsed_ms=elapsed,
            error_type=result.get("error_type", ""),
            input_preview="",
            input_hash_val="",
            extra_meta=_safe_metadata(result),
        )
        return result
    except Exception as exc:
        elapsed = int((time.time() - start) * 1000)
        record_usage(
            session,
            ctx=ctx,
            tool="doctor",
            provider="diagnostic",
            is_ok=False,
            elapsed_ms=elapsed,
            error_type="runtime_error",
            input_preview="",
            input_hash_val="",
        )
        raise
