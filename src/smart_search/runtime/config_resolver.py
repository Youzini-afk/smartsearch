"""Config resolvers – bridge between local config / cloud DB and providers.

* ``LocalConfigResolver`` reads from the existing ``Config`` singleton.
* ``CloudConfigResolver`` reads from the DB (enabled ProviderConfig +
  active ProviderCredential).
Both return ``ResolvedToolConfig`` dataclass instances.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Sequence

from ..config import config as _local_config
from ..security.crypto import decrypt_secret


@dataclass(frozen=True)
class ResolvedToolConfig:
    """Fully resolved config for a single provider instance."""

    provider: str  # e.g. "xai-responses", "exa"
    capability: str  # e.g. "main_search", "docs_search"
    api_url: str
    api_key: str
    model: str = ""
    tools: list[str] = field(default_factory=list)
    settings: dict[str, Any] = field(default_factory=dict)


class LocalConfigResolver:
    """Resolve providers from the existing CLI config (no DB needed)."""

    def resolve(self) -> list[ResolvedToolConfig]:
        results: list[ResolvedToolConfig] = []

        if _local_config.xai_api_key:
            results.append(
                ResolvedToolConfig(
                    provider="xai-responses",
                    capability="main_search",
                    api_url=_local_config.xai_api_url,
                    api_key=_local_config.xai_api_key,
                    model=_local_config.xai_model,
                    tools=_local_config.parse_xai_tools(),
                )
            )

        if _local_config.openai_compatible_api_url and _local_config.openai_compatible_api_key:
            results.append(
                ResolvedToolConfig(
                    provider="openai-compatible",
                    capability="main_search",
                    api_url=_local_config.openai_compatible_api_url,
                    api_key=_local_config.openai_compatible_api_key,
                    model=_local_config.openai_compatible_model,
                )
            )

        if _local_config.exa_api_key:
            results.append(
                ResolvedToolConfig(
                    provider="exa",
                    capability="docs_search",
                    api_url=_local_config.exa_base_url,
                    api_key=_local_config.exa_api_key,
                )
            )

        if _local_config.context7_api_key:
            results.append(
                ResolvedToolConfig(
                    provider="context7",
                    capability="docs_search",
                    api_url=_local_config.context7_base_url,
                    api_key=_local_config.context7_api_key,
                )
            )

        if _local_config.zhipu_api_key:
            results.append(
                ResolvedToolConfig(
                    provider="zhipu",
                    capability="web_search",
                    api_url=_local_config.zhipu_api_url,
                    api_key=_local_config.zhipu_api_key,
                    settings={
                        "search_engine": _local_config.zhipu_search_engine,
                        "timeout": _local_config.zhipu_timeout,
                    },
                )
            )

        return results


class CloudConfigResolver:
    """Resolve providers from DB-backed ProviderConfig + ProviderCredential."""

    def __init__(self, session: Any, tenant_id: str) -> None:
        self._session = session
        self._tenant_id = tenant_id

    def resolve(self) -> list[ResolvedToolConfig]:
        from ..storage.repositories import get_enabled_configs, get_active_credentials
        from ..storage.models import ProviderConfig, ProviderCredential

        db_configs: Sequence[ProviderConfig] = get_enabled_configs(self._session, self._tenant_id)
        results: list[ResolvedToolConfig] = []

        for cfg in db_configs:
            creds = get_active_credentials(self._session, self._tenant_id, cfg.provider)
            if not creds:
                continue
            cred = creds[0]  # primary credential

            api_key = ""
            if cred.encrypted_api_key:
                try:
                    api_key = decrypt_secret(cred.encrypted_api_key)
                except Exception as exc:
                    raise RuntimeError(
                        f"failed to decrypt provider credential {cred.id} for {cfg.provider}"
                    ) from exc

            api_url = ""
            if cred.extra and isinstance(cred.extra, dict):
                api_url = cred.extra.get("api_url", "")

            # Merge settings from config + credential extra
            merged_settings: dict[str, Any] = {}
            if cfg.settings:
                merged_settings.update(cfg.settings)
            if cred.extra and isinstance(cred.extra, dict):
                for k, v in cred.extra.items():
                    if k not in ("api_url", "api_key", "api_secret"):
                        merged_settings.setdefault(k, v)

            model = merged_settings.pop("model", "")
            tools: list[str] = merged_settings.pop("tools", [])

            if not api_url:
                api_url = _default_url_for_provider(cfg.provider)

            results.append(
                ResolvedToolConfig(
                    provider=cfg.provider,
                    capability=cfg.capability,
                    api_url=api_url,
                    api_key=api_key,
                    model=model,
                    tools=tools,
                    settings=merged_settings,
                )
            )

        return results


def _default_url_for_provider(provider: str) -> str:
    """Fallback URLs when not stored in credential extra."""
    _defaults: dict[str, str] = {
        "xai-responses": "https://api.x.ai/v1",
        "openai-compatible": "",
        "exa": "https://api.exa.ai",
        "context7": "https://context7.com",
        "zhipu": "https://open.bigmodel.cn/api",
    }
    return _defaults.get(provider, "")
