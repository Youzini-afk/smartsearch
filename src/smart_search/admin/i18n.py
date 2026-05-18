"""Lightweight i18n for the admin WebUI.

Supports zh-CN (default) and en. Translation dictionaries live in code.
No external i18n dependencies.
"""

from __future__ import annotations

import json as _json
import os
from typing import Any

from fastapi import Request, Response

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

LOCALE_COOKIE = "ss_admin_locale"
DEFAULT_LOCALE = "zh-CN"
SUPPORTED_LOCALES = {"zh-CN", "en"}

# Keys used in JS code – exported as ``js_t`` JSON object for templates.
_JS_KEYS = [
    "common.copied",
    "common.error_prefix",
    "tokens.created",
    "tokens.disabled",
    "tokens.invalid_scopes_json",
    "tokens.confirm_disable",
    "providers.required_fields",
    "providers.credential_created",
    "providers.config_required",
    "providers.config_created",
    "providers.key_revealed",
    "providers.confirm_disable",
    "providers.credential_disabled",
    "providers.invalid_settings_json",
]

# ---------------------------------------------------------------------------
# Translation dictionaries
# ---------------------------------------------------------------------------

_TRANSLATIONS: dict[str, dict[str, str]] = {
    # ------------------------------------------------------------------
    "zh-CN": {
        # nav
        "nav.dashboard": "仪表盘",
        "nav.tokens": "令牌",
        "nav.providers": "提供者",
        "nav.usage": "调用统计",
        "nav.audit": "审计日志",
        "nav.tasks": "任务",
        "nav.system": "系统",
        "nav.logout": "登出",
        "nav.lang_switch": "English",
        # login
        "login.title": "Smart Search 管理后台",
        "login.subtitle": "登录以管理你的部署",
        "login.tab_key": "API 密钥",
        "login.tab_password": "密码",
        "login.api_token": "API 令牌",
        "login.enter_admin_token": "输入具有 admin 权限的 API 令牌",
        "login.sign_in_key": "密钥登录",
        "login.admin_password": "管理密码",
        "login.enter_password": "输入密码",
        "login.password_hint": "通过 SMART_SEARCH_ADMIN_PASSWORD 或 _PASSWORD_HASH 配置",
        "login.sign_in_password": "密码登录",
        "login.auth_failed": "认证失败，请重试。",
        # dashboard
        "dashboard.title": "仪表盘",
        "dashboard.tokens": "令牌",
        "dashboard.provider_credentials": "提供者凭证",
        "dashboard.invocations": "调用次数",
        "dashboard.errors": "错误次数",
        # tokens
        "tokens.title": "API 令牌",
        "tokens.create": "创建令牌",
        "tokens.name": "名称",
        "tokens.prefix": "前缀",
        "tokens.scopes": "权限",
        "tokens.scopes_json": "权限 (JSON)",
        "tokens.status": "状态",
        "tokens.last_used": "最近使用",
        "tokens.created_col": "创建时间",
        "tokens.actions": "操作",
        "tokens.active": "启用",
        "tokens.disabled": "已禁用",
        "tokens.disable": "禁用",
        "tokens.create_title": "创建令牌",
        "tokens.cancel": "取消",
        "tokens.raw_token_shown_once": "原始令牌（仅显示一次）：",
        "tokens.copy": "复制",
        "tokens.created": "令牌已创建！",
        "tokens.disabled_js": "令牌已禁用",
        "tokens.invalid_scopes_json": "权限 JSON 格式无效",
        "tokens.confirm_disable": "确定禁用此令牌？",
        # providers
        "providers.title": "提供者",
        "providers.credentials": "凭证",
        "providers.add_credential": "添加凭证",
        "providers.provider": "提供者",
        "providers.masked_key": "掩码密钥",
        "providers.fingerprint": "指纹",
        "providers.reveal": "查看",
        "providers.enabled": "已启用",
        "providers.add_config": "添加配置",
        "providers.capability": "能力",
        "providers.priority": "优先级",
        "providers.settings": "设置",
        "providers.add_provider_credential": "添加提供者凭证",
        "providers.api_key": "API 密钥",
        "providers.api_secret_optional": "API Secret（可选）",
        "providers.add_provider_config": "添加提供者配置",
        "providers.revealed_credential": "已查看凭证",
        "providers.close": "关闭",
        "providers.show": "显示",
        "providers.required_fields": "提供者和 API 密钥为必填",
        "providers.credential_created": "凭证已创建",
        "providers.config_required": "提供者和能力为必填",
        "providers.config_created": "配置已创建",
        "providers.key_revealed": "密钥已查看（已记录审计事件）",
        "providers.confirm_disable": "确定禁用此凭证？",
        "providers.credential_disabled": "凭证已禁用",
        "providers.invalid_settings_json": "设置 JSON 格式无效",
        # usage
        "usage.title": "工具调用",
        "usage.tool": "工具",
        "usage.provider": "提供者",
        "usage.status": "状态",
        "usage.error": "错误",
        "usage.elapsed_ms": "耗时 (ms)",
        "usage.time": "时间",
        "usage.ok": "成功",
        "usage.error_status": "失败",
        # audit
        "audit.title": "审计事件",
        "audit.action": "操作",
        "audit.actor": "执行者",
        "audit.target_type": "目标类型",
        "audit.target_id": "目标 ID",
        "audit.detail": "详情",
        # tasks
        "tasks.title": "任务",
        "tasks.refresh": "刷新",
        "tasks.id": "ID",
        "tasks.type": "类型",
        "tasks.topic": "主题",
        "tasks.detail": "详情",
        "tasks.no_tasks": "暂无任务。",
        "tasks.task_detail": "任务详情",
        "tasks.pause": "暂停",
        "tasks.cancel": "取消",
        "tasks.resume": "恢复",
        "tasks.retry": "重试",
        "tasks.redo": "重做",
        "tasks.close": "关闭",
        "tasks.loading": "加载中…",
        # system
        "system.title": "系统",
        "system.health": "健康状态",
        "system.database": "数据库",
        "system.mcp_mounted": "MCP 已挂载",
        "system.version": "版本",
        "system.dependencies": "依赖",
        "system.package": "包",
        "system.yes": "是",
        "system.no": "否",
        # common
        "common.copied": "已复制！",
        "common.error_prefix": "错误：",
    },
    # ------------------------------------------------------------------
    "en": {
        # nav
        "nav.dashboard": "Dashboard",
        "nav.tokens": "Tokens",
        "nav.providers": "Providers",
        "nav.usage": "Usage",
        "nav.audit": "Audit",
        "nav.tasks": "Tasks",
        "nav.system": "System",
        "nav.logout": "Logout",
        "nav.lang_switch": "中文",
        # login
        "login.title": "Smart Search Admin",
        "login.subtitle": "Sign in to manage your deployment",
        "login.tab_key": "API Key",
        "login.tab_password": "Password",
        "login.api_token": "API Token",
        "login.enter_admin_token": "Enter an admin-scoped API token",
        "login.sign_in_key": "Sign in with Key",
        "login.admin_password": "Admin Password",
        "login.enter_password": "Enter password",
        "login.password_hint": "Set via SMART_SEARCH_ADMIN_PASSWORD or _PASSWORD_HASH",
        "login.sign_in_password": "Sign in with Password",
        "login.auth_failed": "Authentication failed. Please try again.",
        # dashboard
        "dashboard.title": "Dashboard",
        "dashboard.tokens": "Tokens",
        "dashboard.provider_credentials": "Provider Credentials",
        "dashboard.invocations": "Invocations",
        "dashboard.errors": "Errors",
        # tokens
        "tokens.title": "API Tokens",
        "tokens.create": "Create Token",
        "tokens.name": "Name",
        "tokens.prefix": "Prefix",
        "tokens.scopes": "Scopes",
        "tokens.scopes_json": "Scopes (JSON)",
        "tokens.status": "Status",
        "tokens.last_used": "Last Used",
        "tokens.created_col": "Created",
        "tokens.actions": "Actions",
        "tokens.active": "Active",
        "tokens.disabled": "Disabled",
        "tokens.disable": "Disable",
        "tokens.create_title": "Create Token",
        "tokens.cancel": "Cancel",
        "tokens.raw_token_shown_once": "Raw token (shown only once):",
        "tokens.copy": "Copy",
        "tokens.created": "Token created!",
        "tokens.disabled_js": "Token disabled",
        "tokens.invalid_scopes_json": "Invalid JSON for scopes",
        "tokens.confirm_disable": "Disable this token?",
        # providers
        "providers.title": "Providers",
        "providers.credentials": "Credentials",
        "providers.add_credential": "Add Credential",
        "providers.provider": "Provider",
        "providers.masked_key": "Masked Key",
        "providers.fingerprint": "Fingerprint",
        "providers.reveal": "Reveal",
        "providers.enabled": "Enabled",
        "providers.add_config": "Add Config",
        "providers.capability": "Capability",
        "providers.priority": "Priority",
        "providers.settings": "Settings",
        "providers.add_provider_credential": "Add Provider Credential",
        "providers.api_key": "API Key",
        "providers.api_secret_optional": "API Secret (optional)",
        "providers.add_provider_config": "Add Provider Config",
        "providers.revealed_credential": "Revealed Credential",
        "providers.close": "Close",
        "providers.show": "Show",
        "providers.required_fields": "Provider and API Key required",
        "providers.credential_created": "Credential created",
        "providers.config_required": "Provider and Capability required",
        "providers.config_created": "Config created",
        "providers.key_revealed": "Key revealed (audit event recorded)",
        "providers.confirm_disable": "Disable this credential?",
        "providers.credential_disabled": "Credential disabled",
        "providers.invalid_settings_json": "Invalid JSON for settings",
        # usage
        "usage.title": "Tool Invocations",
        "usage.tool": "Tool",
        "usage.provider": "Provider",
        "usage.status": "Status",
        "usage.error": "Error",
        "usage.elapsed_ms": "Elapsed (ms)",
        "usage.time": "Time",
        "usage.ok": "OK",
        "usage.error_status": "Error",
        # audit
        "audit.title": "Audit Events",
        "audit.action": "Action",
        "audit.actor": "Actor",
        "audit.target_type": "Target Type",
        "audit.target_id": "Target ID",
        "audit.detail": "Detail",
        # tasks
        "tasks.title": "Tasks",
        "tasks.refresh": "Refresh",
        "tasks.id": "ID",
        "tasks.type": "Type",
        "tasks.topic": "Topic",
        "tasks.detail": "Detail",
        "tasks.no_tasks": "No tasks found.",
        "tasks.task_detail": "Task Detail",
        "tasks.pause": "Pause",
        "tasks.cancel": "Cancel",
        "tasks.resume": "Resume",
        "tasks.retry": "Retry",
        "tasks.redo": "Redo",
        "tasks.close": "Close",
        "tasks.loading": "Loading…",
        # system
        "system.title": "System",
        "system.health": "Health",
        "system.database": "Database",
        "system.mcp_mounted": "MCP Mounted",
        "system.version": "Version",
        "system.dependencies": "Dependencies",
        "system.package": "Package",
        "system.yes": "Yes",
        "system.no": "No",
        # common
        "common.copied": "Copied!",
        "common.error_prefix": "Error: ",
    },
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_locale(request: Request) -> str:
    """Determine locale from: ?lang= → cookie → Accept-Language → default."""
    # 1. Query param (highest priority – triggers cookie set + redirect)
    lang = request.query_params.get("lang")
    if lang in SUPPORTED_LOCALES:
        return lang

    # 2. Cookie
    cookie = request.cookies.get(LOCALE_COOKIE)
    if cookie in SUPPORTED_LOCALES:
        return cookie

    # 3. Accept-Language header
    accept = request.headers.get("accept-language", "").lower()
    if "zh" in accept:
        return "zh-CN"
    if "en" in accept:
        return "en"

    # 4. Default
    return DEFAULT_LOCALE


def set_locale_cookie(response: Response, locale: str) -> None:
    """Set the locale preference cookie."""
    secure_env = os.getenv("SMART_SEARCH_ADMIN_COOKIE_SECURE")
    if secure_env is not None:
        secure = secure_env.lower() == "true"
    else:
        secure = os.getenv("SMART_SEARCH_ALLOW_INSECURE_DEV_KEYS") != "true"
    response.set_cookie(
        key=LOCALE_COOKIE,
        value=locale,
        max_age=3600 * 24 * 365,
        path="/admin",
        httponly=False,
        samesite="strict",
        secure=secure,
    )


def t(key: str, locale: str = DEFAULT_LOCALE, **kwargs: Any) -> str:
    """Translate *key* for *locale*, with optional ``str.format`` kwargs."""
    translations = _TRANSLATIONS.get(locale, {})
    text = translations.get(key, key)
    if kwargs:
        try:
            text = text.format(**kwargs)
        except (KeyError, IndexError):
            pass
    return text


def _build_js_t(locale: str) -> str:
    """Build a JSON string of JS-facing translations for *locale*."""
    translations = _TRANSLATIONS.get(locale, {})
    obj = {k: translations.get(k, k) for k in _JS_KEYS}
    return _json.dumps(obj, ensure_ascii=False)


def get_i18n_context(request: Request) -> dict[str, Any]:
    """Return a dict of i18n template variables for *request*.

    Keys: ``t``, ``locale``, ``other_locale``, ``other_locale_label``, ``js_t``.
    """
    locale = get_locale(request)
    other = "en" if locale == "zh-CN" else "zh-CN"
    other_label = "English" if locale == "zh-CN" else "中文"
    return {
        "t": lambda key, **kw: t(key, locale=locale, **kw),
        "locale": locale,
        "other_locale": other,
        "other_locale_label": other_label,
        "js_t": _build_js_t(locale),
    }


def check_lang_redirect(request: Request) -> Response | None:
    """If ``?lang=`` is present, set locale cookie and redirect without it.

    Returns a ``RedirectResponse`` or ``None``.
    """
    from fastapi.responses import RedirectResponse

    lang = request.query_params.get("lang")
    if lang not in SUPPORTED_LOCALES:
        return None

    # Build URL without the lang param
    path = str(request.url.path)
    remaining = []
    for k, v in request.query_params.items():
        if k != "lang":
            remaining.append(f"{k}={v}")
    qs = "&".join(remaining)
    url = path + ("?" + qs if qs else "")

    resp = RedirectResponse(url=url, status_code=302)
    set_locale_cookie(resp, lang)
    return resp
