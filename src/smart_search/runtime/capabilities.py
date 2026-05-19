"""Capability metadata for admin/runtime configuration surfaces.

This module intentionally separates two concepts that were previously blurred in
the admin UI:

* the currently effective Smart Search runtime behavior, which is still driven
  by ``config.py`` and ``service.py``;
* DB-backed cloud capability overrides, which are persisted by the admin UI but
  are not yet consumed by the service execution layer.

Keeping this metadata in Python (rather than Jinja/JS defaults) prevents the UI
from inventing runtime defaults that drift away from the real project behavior.
"""

from __future__ import annotations

from typing import Any

from ..config import config


def _source(key: str) -> str:
    return config.get_config_source(key)


def _runtime_field(value: Any, source: str, *, note: str = "") -> dict[str, Any]:
    return {
        "value": value,
        "source": source,
        "effective": True,
        "note": note,
    }


def _safe_value(getter: Any, fallback: Any, *, source: str = "invalid_config") -> tuple[Any, str, str]:
    try:
        return getter(), source, ""
    except Exception as exc:  # defensive for admin pages: never 500 on bad config
        return fallback, source, str(exc)


def get_capability_definitions() -> dict[str, dict[str, Any]]:
    """Return the canonical admin-facing capability definitions.

    ``db_overrides_effective`` is deliberately false for now: cloud
    ``ProviderConfig`` rows are resolved and carried on request context, but the
    current tool runtime still delegates to ``service.py`` functions that read
    the global ``Config`` singleton.
    """

    return {
        "main_search": {
            "label_key": "config.main_search",
            "tag": "main_search",
            "commands": ["search"],
            "providers": ["xai-responses", "openai-compatible"],
            "runtime_path": "service.py:_main_search_provider_configs/search",
            "db_overrides_effective": False,
            "stored_fields": [
                "provider chain",
                "model",
                "validation",
                "fallback",
                "result limit",
                "timeout",
            ],
        },
        "docs_search": {
            "label_key": "config.docs_search",
            "tag": "docs_search",
            "commands": ["exa-search", "context7-library", "context7-docs"],
            "providers": ["exa", "context7"],
            "runtime_path": "service.py:_run_docs_search_fallback/exa_search/context7_*",
            "db_overrides_effective": False,
            "stored_fields": ["provider", "max_results", "timeout", "context7"],
        },
        "web_search": {
            "label_key": "config.web_search",
            "tag": "web_search",
            "commands": ["zhipu-search", "search supplemental web_search"],
            "providers": ["zhipu", "tavily", "firecrawl"],
            "runtime_path": "service.py:zhipu_search/_run_extra_sources",
            "db_overrides_effective": False,
            "stored_fields": ["provider", "count", "search_engine", "timeout"],
        },
        "web_fetch": {
            "label_key": "config.web_fetch",
            "tag": "web_fetch",
            "commands": ["fetch"],
            "providers": ["tavily", "firecrawl"],
            "runtime_path": "service.py:fetch/call_tavily_extract/call_firecrawl_scrape",
            "db_overrides_effective": False,
            "stored_fields": ["provider", "timeout", "render_js", "content_limit", "format"],
        },
        "deep_planner": {
            "label_key": "config.deep_planner",
            "tag": "deep_planner",
            "commands": ["deep", "dr"],
            "providers": [],
            "runtime_path": "service.py:build_deep_research_plan",
            "db_overrides_effective": False,
            "stored_fields": ["budget", "max_steps"],
        },
    }


def get_effective_capabilities() -> dict[str, dict[str, Any]]:
    """Describe currently effective runtime behavior and config sources."""

    configured_main: list[str] = []
    if config.xai_api_key:
        configured_main.append("xai-responses")
    if config.openai_compatible_api_url and config.openai_compatible_api_key:
        configured_main.append("openai-compatible")

    validation, validation_source, validation_note = _safe_value(
        lambda: config.validation_level,
        "invalid",
        source=_source("SMART_SEARCH_VALIDATION_LEVEL"),
    )
    fallback_mode, fallback_source, fallback_note = _safe_value(
        lambda: config.fallback_mode,
        "invalid",
        source=_source("SMART_SEARCH_FALLBACK_MODE"),
    )
    xai_tools, tools_source, tools_note = _safe_value(
        lambda: ",".join(config.parse_xai_tools()),
        "invalid",
        source=_source("XAI_TOOLS"),
    )

    main_summary = (
        f"Configured: {', '.join(configured_main)}; fallback chain: xai-responses -> openai-compatible"
        if configured_main
        else "Not configured; fallback chain: xai-responses -> openai-compatible"
    )
    docs_configured = [name for name, key in (("exa", config.exa_api_key), ("context7", config.context7_api_key)) if key]
    web_search_configured = [name for name, key in (("zhipu", config.zhipu_api_key), ("tavily", config.tavily_api_key), ("firecrawl", config.firecrawl_api_key)) if key]
    web_fetch_configured = [name for name, key in (("tavily", config.tavily_api_key), ("firecrawl", config.firecrawl_api_key)) if key]

    return {
        "main_search": {
            "summary": main_summary,
            "source": "service.py fallback chain + config.py",
            "fields": {
                "model": _runtime_field(config.xai_model, _source("XAI_MODEL")),
                "validation": _runtime_field(validation, validation_source, note=validation_note),
                "fallback_mode": _runtime_field(fallback_mode, fallback_source, note=fallback_note),
                "xai_tools": _runtime_field(xai_tools, tools_source, note=tools_note),
            },
        },
        "docs_search": {
            "summary": (
                f"Configured: {', '.join(docs_configured)}; fallback chain: Exa -> Context7"
                if docs_configured
                else "Not configured; fallback chain: Exa -> Context7"
            ),
            "source": "service.py docs fallback chain",
            "fields": {
                "exa_num_results": _runtime_field(5, "service.py exa/docs default"),
                "exa_timeout_seconds": _runtime_field(config.exa_timeout, _source("EXA_TIMEOUT_SECONDS")),
                "context7_timeout_seconds": _runtime_field(config.context7_timeout, _source("CONTEXT7_TIMEOUT_SECONDS")),
            },
        },
        "web_search": {
            "summary": (
                f"Configured: {', '.join(web_search_configured)}; supplemental chain: Zhipu / Tavily / Firecrawl"
                if web_search_configured
                else "Not configured; supplemental chain: Zhipu / Tavily / Firecrawl"
            ),
            "source": "service.py intent routing",
            "fields": {
                "zhipu_count": _runtime_field(10, "service.py zhipu-search default"),
                "zhipu_search_engine": _runtime_field(config.zhipu_search_engine, _source("ZHIPU_SEARCH_ENGINE")),
                "zhipu_timeout_seconds": _runtime_field(config.zhipu_timeout, _source("ZHIPU_TIMEOUT_SECONDS")),
            },
        },
        "web_fetch": {
            "summary": (
                f"Configured: {', '.join(web_fetch_configured)}; fallback chain: Tavily extract -> Firecrawl scrape"
                if web_fetch_configured
                else "Not configured; fallback chain: Tavily extract -> Firecrawl scrape"
            ),
            "source": "service.py fetch fallback chain",
            "fields": {
                "tavily_timeout_seconds": _runtime_field(config.tavily_timeout, _source("TAVILY_TIMEOUT_SECONDS")),
                "firecrawl_timeout_seconds": _runtime_field(90, "service.py call_firecrawl_scrape"),
            },
        },
        "deep_planner": {
            "summary": "Offline planner; does not call providers by default",
            "source": "service.py build_deep_research_plan",
            "fields": {
                "budget": _runtime_field("standard", "service.py default"),
            },
        },
    }


def normalize_capability_id(capability: str) -> str:
    """Normalize historical/admin aliases to canonical capability IDs."""

    if capability == "fetch":
        return "web_fetch"
    return capability
