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
    "common.saved",
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
        "nav.brand": "Smart Search",
        "nav.dashboard": "仪表盘",
        "nav.tokens": "API 令牌",
        "nav.providers": "提供者",
        "nav.usage": "调用统计",
        "nav.audit": "审计日志",
        "nav.tasks": "Deep Research",
        "nav.system": "系统",
        "nav.settings": "系统设置",
        "nav.logout": "登出",
        "nav.lang_switch": "English",
        "nav.group_core": "核心",
        "nav.group_config": "配置",
        "nav.group_monitor": "监控",
        "nav.group_system": "系统",
        # login
        "login.title": "Smart Search 管理后台",
        "login.subtitle": "登录以管理你的私有搜索平台",
        "login.tab_key": "API 密钥",
        "login.tab_password": "密码",
        "login.api_token": "API 令牌",
        "login.enter_admin_token": "输入具有 admin 权限的 API 令牌",
        "login.sign_in_key": "密钥登录",
        "login.admin_password": "管理密码",
        "login.enter_password": "输入密码",
        "login.password_hint": "通过 SMART_SEARCH_ADMIN_PASSWORD 或 _PASSWORD_HASH 配置",
        "login.sign_in_password": "密码登录",
        "login.auth_failed": "认证失败，请检查凭据后重试。",
        # dashboard
        "dashboard.title": "仪表盘",
        "dashboard.subtitle": "部署运行概览",
        "dashboard.tokens": "令牌",
        "dashboard.provider_credentials": "提供者凭证",
        "dashboard.invocations": "调用次数",
        "dashboard.errors": "错误次数",
        "dashboard.success_rate": "成功率",
        "dashboard.errors_count": "错误 {count} 次",
        "dashboard.avg_latency": "平均延迟",
        "dashboard.active_providers": "活跃提供者",
        "dashboard.active_tokens": "活跃令牌",
        "dashboard.tasks_running": "运行中任务",
        "dashboard.by_tool": "按工具分布",
        "dashboard.provider_health": "提供者健康",
        "dashboard.no_data_yet": "暂无数据",
        "dashboard.trend_24h": "24 小时趋势",
        "dashboard.deep_research": "深度研究",
        "dashboard.view_all": "查看全部",
        "dashboard.recent_errors": "近期错误",
        "dashboard.vs_yesterday": "较昨日",
        "dashboard.success_rate": "成功率",
        "dashboard.avg_latency": "平均延迟",
        "dashboard.active_tokens": "活跃令牌",
        "dashboard.errors_count": "{count} 次错误",
        "dashboard.vs_yesterday": "较昨日",
        "dashboard.by_tool": "按工具分类",
        "dashboard.provider_health": "提供者健康",
        "dashboard.trend_24h": "24 小时趋势",
        "dashboard.deep_research": "Deep Research",
        "dashboard.view_all": "查看全部",
        "dashboard.recent_errors": "最近错误",
        "dashboard.no_data_yet": "暂无数据",
        "dashboard.active_providers": "活跃提供者",
        "dashboard.tasks_running": "运行中任务",
        # tokens
        "tokens.title": "API 令牌",
        "tokens.subtitle": "管理访问密钥和权限",
        "tokens.create": "创建令牌",
        "tokens.name": "名称",
        "tokens.prefix": "前缀",
        "tokens.scopes": "权限",
        "tokens.scopes_json": "权限 (JSON)",
        "tokens.scopes_hint": "可自定义 JSON 或点击上方模板按钮快速设置",
        "tokens.status": "状态",
        "tokens.last_used": "最近使用",
        "tokens.created_col": "创建时间",
        "tokens.expires": "过期时间",
        "tokens.actions": "操作",
        "tokens.active": "启用",
        "tokens.disabled": "已禁用",
        "tokens.disable": "禁用",
        "tokens.create_title": "创建新令牌",
        "tokens.cancel": "取消",
        "tokens.raw_token_shown_once": "⚠️ 原始令牌仅显示一次，请立即保存！",
        "tokens.copy": "复制",
        "tokens.created": "令牌已创建！",
        "tokens.disabled_js": "令牌已禁用",
        "tokens.invalid_scopes_json": "权限 JSON 格式无效",
        "tokens.confirm_disable": "确定禁用此令牌？",
        "tokens.search_tokens": "搜索令牌名称...",
        "tokens.no_tokens": "暂无 API 令牌。点击上方按钮创建第一个令牌。",
        "tokens.scope_admin": "管理员",
        "tokens.scope_search": "搜索",
        "tokens.scope_fetch": "抓取",
        "tokens.scope_deep": "深度研究",
        "tokens.scope_readonly": "只读",
        # providers
        "providers.title": "提供者配置",
        "providers.subtitle": "管理搜索 API 提供者的凭证和能力",
        "providers.credentials": "凭证",
        "providers.add_credential": "添加凭证",
        "providers.provider": "提供者",
        "providers.masked_key": "密钥",
        "providers.fingerprint": "指纹",
        "providers.reveal": "查看",
        "providers.enabled": "已启用",
        "providers.add_config": "添加能力配置",
        "providers.capability": "能力",
        "providers.priority": "优先级",
        "providers.settings": "设置",
        "providers.edit": "编辑",
        "providers.add_provider_credential": "添加提供者凭证",
        "providers.api_key": "API 密钥",
        "providers.api_secret_optional": "API Secret（可选）",
        "providers.add_provider_config": "添加能力配置",
        "providers.edit_config": "编辑能力配置",
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
        "providers.no_credential": "未配置凭证",
        "providers.search_providers": "搜索提供者...",
        "providers.no_providers": "暂无提供者。添加凭证以开始配置。",
        "providers.add_capability": "添加能力",
        "providers.provider_hint": "唯一标识符，如 xai-responses、openai、brave",
        "providers.model": "模型",
        "providers.api_url": "API 地址",
        "providers.timeout": "超时 (秒)",
        "providers.max_results": "最大结果数",
        "providers.tools": "可用工具 (逗号分隔)",
        "providers.settings_extra": "其他设置 (JSON)",
        "providers.settings_extra_hint": "高级设置可在此添加，将合并到上方普通字段",
        # usage
        "usage.title": "调用统计",
        "usage.subtitle": "工具调用和性能监控",
        "usage.tool": "工具",
        "usage.provider": "提供者",
        "usage.status": "状态",
        "usage.error": "错误",
        "usage.elapsed_ms": "耗时 (ms)",
        "usage.time": "时间",
        "usage.ok": "成功",
        "usage.error_status": "失败",
        "usage.total_invocations": "总调用",
        "usage.success_rate": "成功率",
        "usage.avg_latency": "平均延迟",
        "usage.errors": "错误数",
        "usage.by_tool": "按工具分布",
        "usage.by_provider": "按提供者分布",
        "usage.error_breakdown": "错误明细",
        "usage.detail": "调用明细",
        "usage.records": "条记录",
        # audit
        "audit.title": "审计日志",
        "audit.subtitle": "安全和操作事件记录",
        "audit.events": "审计事件",
        "audit.action": "操作",
        "audit.actor": "执行者",
        "audit.target_type": "目标类型",
        "audit.target_id": "目标 ID",
        "audit.detail": "详情",
        # tasks
        "tasks.title": "Deep Research 任务",
        "tasks.subtitle": "深度研究任务的管理和监控",
        "tasks.refresh": "刷新",
        "tasks.id": "ID",
        "tasks.type": "类型",
        "tasks.topic": "主题",
        "tasks.detail": "详情",
        "tasks.no_tasks": "暂无任务。通过 API 提交 Deep Research 任务后即可在此查看。",
        "tasks.task_detail": "任务详情",
        "tasks.pause": "暂停",
        "tasks.cancel": "取消",
        "tasks.resume": "恢复",
        "tasks.retry": "重试",
        "tasks.redo": "重做",
        "tasks.close": "关闭",
        "tasks.loading": "加载中…",
        "tasks.running": "运行中",
        "tasks.queued": "排队中",
        "tasks.paused": "已暂停",
        "tasks.completed": "已完成",
        "tasks.failed": "失败",
        "tasks.cancelled": "已取消",
        "tasks.in_progress": "执行中…",
        # system
        "system.title": "系统",
        "system.subtitle": "系统状态和配置",
        "system.health": "健康状态",
        "system.database": "数据库",
        "system.mcp_mounted": "MCP 已挂载",
        "system.version": "版本",
        "system.dependencies": "依赖",
        "system.package": "包",
        "system.yes": "是",
        "system.no": "否",
        "system.all_operational": "所有系统运行正常",
        "system.uptime": "运行时间",
        "system.settings_config": "配置",
        "system.log_level": "日志级别",
        "system.request_timeout": "请求超时 (秒)",
        "system.timeout_hint": "上游 API 请求超时时间",
        "system.settings_readonly": "配置项为只读展示，功能尚未接入",
        # common
        "common.copied": "已复制！",
        "common.error_prefix": "错误：",
        "common.save": "保存",
        "common.saved": "已保存",
    },
    # ------------------------------------------------------------------
    "en": {
        # nav
        "nav.brand": "Smart Search",
        "nav.dashboard": "Dashboard",
        "nav.tokens": "API Tokens",
        "nav.providers": "Providers",
        "nav.usage": "Usage",
        "nav.audit": "Audit",
        "nav.tasks": "Deep Research",
        "nav.system": "System",
        "nav.settings": "Settings",
        "nav.logout": "Logout",
        "nav.lang_switch": "中文",
        "nav.group_core": "Core",
        "nav.group_config": "Configuration",
        "nav.group_monitor": "Monitoring",
        "nav.group_system": "System",
        # login
        "login.title": "Smart Search Admin",
        "login.subtitle": "Sign in to manage your private search platform",
        "login.tab_key": "API Key",
        "login.tab_password": "Password",
        "login.api_token": "API Token",
        "login.enter_admin_token": "Enter an admin-scoped API token",
        "login.sign_in_key": "Sign in with Key",
        "login.admin_password": "Admin Password",
        "login.enter_password": "Enter password",
        "login.password_hint": "Set via SMART_SEARCH_ADMIN_PASSWORD or _PASSWORD_HASH",
        "login.sign_in_password": "Sign in with Password",
        "login.auth_failed": "Authentication failed. Please check your credentials.",
        # dashboard
        "dashboard.title": "Dashboard",
        "dashboard.subtitle": "Deployment overview",
        "dashboard.tokens": "Tokens",
        "dashboard.provider_credentials": "Provider Credentials",
        "dashboard.invocations": "Invocations",
        "dashboard.errors": "Errors",
        "dashboard.success_rate": "Success Rate",
        "dashboard.errors_count": "{count} errors",
        "dashboard.avg_latency": "Avg Latency",
        "dashboard.active_providers": "Active Providers",
        "dashboard.active_tokens": "Active Tokens",
        "dashboard.tasks_running": "Running Tasks",
        "dashboard.by_tool": "By Tool",
        "dashboard.provider_health": "Provider Health",
        "dashboard.no_data_yet": "No data yet",
        "dashboard.trend_24h": "24h Trend",
        "dashboard.deep_research": "Deep Research",
        "dashboard.view_all": "View All",
        "dashboard.recent_errors": "Recent Errors",
        "dashboard.vs_yesterday": "vs yesterday",
        "dashboard.success_rate": "Success Rate",
        "dashboard.avg_latency": "Avg Latency",
        "dashboard.active_tokens": "Active Tokens",
        "dashboard.errors_count": "{count} errors",
        "dashboard.vs_yesterday": "vs yesterday",
        "dashboard.by_tool": "By Tool",
        "dashboard.provider_health": "Provider Health",
        "dashboard.trend_24h": "24h Trend",
        "dashboard.deep_research": "Deep Research",
        "dashboard.view_all": "View All",
        "dashboard.recent_errors": "Recent Errors",
        "dashboard.no_data_yet": "No data yet",
        "dashboard.active_providers": "Active Providers",
        "dashboard.tasks_running": "Running Tasks",
        # tokens
        "tokens.title": "API Tokens",
        "tokens.subtitle": "Manage access keys and permissions",
        "tokens.create": "Create Token",
        "tokens.name": "Name",
        "tokens.prefix": "Prefix",
        "tokens.scopes": "Scopes",
        "tokens.scopes_json": "Scopes (JSON)",
        "tokens.scopes_hint": "Customize JSON or use template buttons above",
        "tokens.status": "Status",
        "tokens.last_used": "Last Used",
        "tokens.created_col": "Created",
        "tokens.expires": "Expires",
        "tokens.actions": "Actions",
        "tokens.active": "Active",
        "tokens.disabled": "Disabled",
        "tokens.disable": "Disable",
        "tokens.create_title": "Create Token",
        "tokens.cancel": "Cancel",
        "tokens.raw_token_shown_once": "⚠️ Raw token shown only once — save it now!",
        "tokens.copy": "Copy",
        "tokens.created": "Token created!",
        "tokens.disabled_js": "Token disabled",
        "tokens.invalid_scopes_json": "Invalid JSON for scopes",
        "tokens.confirm_disable": "Disable this token?",
        "tokens.search_tokens": "Search tokens...",
        "tokens.no_tokens": "No API tokens yet. Click the button above to create one.",
        "tokens.scope_admin": "Admin",
        "tokens.scope_search": "Search",
        "tokens.scope_fetch": "Fetch",
        "tokens.scope_deep": "Deep Research",
        "tokens.scope_readonly": "Read Only",
        # providers
        "providers.title": "Providers",
        "providers.subtitle": "Manage search API provider credentials and capabilities",
        "providers.credentials": "Credentials",
        "providers.add_credential": "Add Credential",
        "providers.provider": "Provider",
        "providers.masked_key": "Key",
        "providers.fingerprint": "Fingerprint",
        "providers.reveal": "Reveal",
        "providers.enabled": "Enabled",
        "providers.add_config": "Add Capability Config",
        "providers.capability": "Capability",
        "providers.priority": "Priority",
        "providers.settings": "Settings",
        "providers.edit": "Edit",
        "providers.add_provider_credential": "Add Provider Credential",
        "providers.api_key": "API Key",
        "providers.api_secret_optional": "API Secret (optional)",
        "providers.add_provider_config": "Add Capability Config",
        "providers.edit_config": "Edit Capability Config",
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
        "providers.no_credential": "No credential configured",
        "providers.search_providers": "Search providers...",
        "providers.no_providers": "No providers yet. Add a credential to get started.",
        "providers.add_capability": "Add Capability",
        "providers.provider_hint": "Unique identifier, e.g. xai-responses, openai, brave",
        "providers.model": "Model",
        "providers.api_url": "API URL",
        "providers.timeout": "Timeout (s)",
        "providers.max_results": "Max Results",
        "providers.tools": "Tools (comma-separated)",
        "providers.settings_extra": "Extra Settings (JSON)",
        "providers.settings_extra_hint": "Advanced settings merged with fields above",
        # usage
        "usage.title": "Usage",
        "usage.subtitle": "Tool invocation and performance monitoring",
        "usage.tool": "Tool",
        "usage.provider": "Provider",
        "usage.status": "Status",
        "usage.error": "Error",
        "usage.elapsed_ms": "Elapsed (ms)",
        "usage.time": "Time",
        "usage.ok": "OK",
        "usage.error_status": "Error",
        "usage.total_invocations": "Total Invocations",
        "usage.success_rate": "Success Rate",
        "usage.avg_latency": "Avg Latency",
        "usage.errors": "Errors",
        "usage.by_tool": "By Tool",
        "usage.by_provider": "By Provider",
        "usage.error_breakdown": "Error Breakdown",
        "usage.detail": "Detail",
        "usage.records": "records",
        # audit
        "audit.title": "Audit Log",
        "audit.subtitle": "Security and operation event log",
        "audit.events": "Audit Events",
        "audit.action": "Action",
        "audit.actor": "Actor",
        "audit.target_type": "Target Type",
        "audit.target_id": "Target ID",
        "audit.detail": "Detail",
        # tasks
        "tasks.title": "Deep Research Tasks",
        "tasks.subtitle": "Monitor and manage deep research tasks",
        "tasks.refresh": "Refresh",
        "tasks.id": "ID",
        "tasks.type": "Type",
        "tasks.topic": "Topic",
        "tasks.detail": "Detail",
        "tasks.no_tasks": "No tasks found. Submit a Deep Research task via API to see it here.",
        "tasks.task_detail": "Task Detail",
        "tasks.pause": "Pause",
        "tasks.cancel": "Cancel",
        "tasks.resume": "Resume",
        "tasks.retry": "Retry",
        "tasks.redo": "Redo",
        "tasks.close": "Close",
        "tasks.loading": "Loading…",
        "tasks.running": "Running",
        "tasks.queued": "Queued",
        "tasks.paused": "Paused",
        "tasks.completed": "Completed",
        "tasks.failed": "Failed",
        "tasks.cancelled": "Cancelled",
        "tasks.in_progress": "In progress…",
        # system
        "system.title": "System",
        "system.subtitle": "System status and configuration",
        "system.health": "Health",
        "system.database": "Database",
        "system.mcp_mounted": "MCP Mounted",
        "system.version": "Version",
        "system.dependencies": "Dependencies",
        "system.package": "Package",
        "system.yes": "Yes",
        "system.no": "No",
        "system.all_operational": "All systems operational",
        "system.uptime": "Uptime",
        "system.settings_config": "Configuration",
        "system.log_level": "Log Level",
        "system.request_timeout": "Request Timeout (s)",
        "system.timeout_hint": "Upstream API request timeout",
        "system.settings_readonly": "Settings shown as read-only, backend not yet connected",
        # common
        "common.copied": "Copied!",
        "common.error_prefix": "Error: ",
        "common.save": "Save",
        "common.saved": "Saved",
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
