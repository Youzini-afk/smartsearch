"""Provider factory – create provider instances from ResolvedToolConfig."""

from __future__ import annotations

from typing import Any

from .config_resolver import ResolvedToolConfig


def create_provider(rtc: ResolvedToolConfig) -> Any:
    """Instantiate a provider from a resolved config.

    Returns an existing provider class instance.  Does **not** modify
    ``service.py`` – Phase 2 will integrate this more deeply.
    """
    provider = rtc.provider

    if provider == "xai-responses":
        from ..providers.xai_responses import XAIResponsesSearchProvider

        return XAIResponsesSearchProvider(
            api_url=rtc.api_url,
            api_key=rtc.api_key,
            model=rtc.model or "grok-4-fast",
            tools=rtc.tools or ["web_search", "x_search"],
        )

    if provider == "openai-compatible":
        from ..providers.openai_compatible import OpenAICompatibleSearchProvider

        return OpenAICompatibleSearchProvider(
            api_url=rtc.api_url,
            api_key=rtc.api_key,
            model=rtc.model or "gpt-4o",
        )

    if provider == "exa":
        from ..providers.exa import ExaSearchProvider

        return ExaSearchProvider(
            api_url=rtc.api_url,
            api_key=rtc.api_key,
        )

    if provider == "context7":
        from ..providers.context7 import Context7Provider

        return Context7Provider(
            api_url=rtc.api_url,
            api_key=rtc.api_key,
            timeout=rtc.settings.get("timeout", 30.0),
        )

    if provider == "zhipu":
        from ..providers.zhipu import ZhipuWebSearchProvider

        return ZhipuWebSearchProvider(
            api_url=rtc.api_url,
            api_key=rtc.api_key,
        )

    raise ValueError(f"Unknown provider: {provider}")


def create_providers(configs: list[ResolvedToolConfig]) -> list[Any]:
    """Create multiple provider instances from resolved configs."""
    return [create_provider(rtc) for rtc in configs]
