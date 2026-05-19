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
    "config.confirm_clear_overrides",
]

# ---------------------------------------------------------------------------
# Translation dictionaries
# ---------------------------------------------------------------------------

_TRANSLATIONS: dict[str, dict[str, str]] = {
    # ------------------------------------------------------------------
    "zh-CN": {
        # nav
        "nav.brand": "智搜云管理",
        "nav.sub_brand": "私有云 MCP 平台",
        "nav.dashboard": "仪表盘",
        "nav.config_center": "配置中心",
        "nav.monitor": "服务监控",
        "nav.tokens": "API 令牌",
        "nav.providers": "提供商密钥",
        "nav.usage": "调用统计",
        "nav.audit": "审计日志",
        "nav.tasks": "Deep Research",
        "nav.system": "系统设置",
        "nav.settings": "系统设置",
        "nav.logout": "登出",
        "nav.lang_switch": "English",
        "nav.group_core": "核心",
        "nav.group_config": "配置",
        "nav.group_monitor": "监控",
        "nav.group_system": "系统",
        "nav.console": "控制台",
        "nav.function_config": "功能配置",
        "nav.global_audit": "全局审计",
        "nav.api_docs": "API 文档",
        "nav.resources": "资源",
        "nav.docs": "文档中心",
        "nav.profile": "个人设置",
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
        "dashboard.provider_credentials": "提供商凭证",
        "dashboard.invocations": "调用次数",
        "dashboard.errors": "错误次数",
        "dashboard.success_rate": "成功率",
        "dashboard.errors_count": "错误 {count} 次",
        "dashboard.avg_latency": "平均延迟",
        "dashboard.active_providers": "活跃提供商",
        "dashboard.active_tokens": "活跃令牌",
        "dashboard.tasks_running": "运行中任务",
        "dashboard.by_tool": "按工具分布",
        "dashboard.provider_health": "提供商健康",
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
        "dashboard.provider_health": "提供商健康",
        "dashboard.trend_24h": "24 小时趋势",
        "dashboard.deep_research": "Deep Research",
        "dashboard.view_all": "查看全部",
        "dashboard.recent_errors": "最近错误",
        "dashboard.no_data_yet": "暂无数据",
        "dashboard.active_providers": "活跃提供商",
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
        # providers (提供商密钥)
        "providers.title": "提供商密钥",
        "providers.subtitle": "管理各 API 提供商的访问密钥和凭证",
        "providers.credentials": "凭证",
        "providers.add_credential": "添加密钥",
        "providers.provider": "提供商",
        "providers.masked_key": "密钥",
        "providers.fingerprint": "指纹",
        "providers.reveal": "查看",
        "providers.enabled": "已启用",
        "providers.enable": "启用",
        "providers.add_config": "添加能力配置",
        "providers.capability": "能力",
        "providers.priority": "优先级",
        "providers.settings": "设置",
        "providers.edit": "编辑",
        "providers.add_provider_credential": "添加提供商密钥",
        "providers.api_key": "API 密钥",
        "providers.api_secret_optional": "API Secret（可选）",
        "providers.add_provider_config": "添加能力配置",
        "providers.edit_config": "编辑能力配置",
        "providers.revealed_credential": "已查看凭证",
        "providers.close": "关闭",
        "providers.show": "显示",
        "providers.required_fields": "提供商和 API 密钥为必填",
        "providers.credential_created": "凭证已创建",
        "providers.credential_enabled": "凭证已启用",
        "providers.config_required": "提供商和能力为必填",
        "providers.config_created": "配置已创建",
        "providers.key_revealed": "密钥已查看（已记录审计事件）",
        "providers.confirm_disable": "确定禁用此凭证？",
        "providers.credential_disabled": "凭证已禁用",
        "providers.invalid_settings_json": "设置 JSON 格式无效",
        "providers.no_credential": "未配置凭证",
        "providers.search_providers": "搜索提供商...",
        "providers.no_providers": "暂无提供商密钥。添加密钥以开始配置。",
        "providers.add_capability": "添加能力",
        "providers.provider_hint": "选择或自定义提供商标识",
        "providers.custom": "自定义",
        "providers.custom_provider_name": "自定义提供商名称",
        "providers.test": "测试",
        "providers.testing": "正在测试",
        "providers.test_ok": "连接正常",
        "providers.test_fail": "连接失败",
        "providers.remark": "备注",
        "providers.remark_placeholder": "例如：生产环境密钥",
        "providers.algorithm": "加密算法",
        "providers.go_to_config": "前往功能配置",
        "providers.base_url": "API 地址 / Base URL",
        "providers.base_url_custom_hint": "自定义提供商或 OpenAI 兼容提供商必须填写 API 地址",
        "providers.base_url_openai_hint": "可选：自定义 OpenAI 兼容端点地址",
        "providers.base_url_optional_hint": "可选：覆盖默认 API 地址",
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
        "usage.provider": "提供商",
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
        "usage.by_provider": "按提供商分布",
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
        "system.title": "系统设置",
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
        # config (功能配置)
        "config.title": "功能配置",
        "config.subtitle": "按 Smart Search 能力配置使用的渠道、模型、Fallback 和执行参数",
        "config.clear_overrides": "清空覆盖",
        "config.save_overrides": "保存覆盖",
        "config.main_search": "主搜索",
        "config.docs_search": "文档搜索",
        "config.web_search": "网页搜索",
        "config.web_fetch": "网页抓取",
        "config.deep_planner": "Deep Planner",
        "config.enable_validation": "启用验证",
        "config.primary_channel": "首选渠道",
        "config.fallback_channel": "FALLBACK 渠道",
        "config.select_provider": "选择提供商",
        "config.none": "无",
        "config.model": "模型 (MODEL)",
        "config.max_results": "最大结果数",
        "config.max_items": "最大条数",
        "config.timeout_ms": "超时 (MS)",
        "config.timeout_s": "超时 (s)",
        "config.render_js": "JS 渲染",
        "config.fetch_channel": "抓取渠道",
        "config.content_limit": "正文长度限制",
        "config.format": "输出格式",
        "config.library_id": "文档库 ID",
        "config.provider_status": "提供商状态",
        "config.live_status": "实时",
        "config.credentials_only": "密钥状态",
        "config.manage_credentials": "管理密钥",
        "config.no_providers_configured": "暂未配置提供商",
        "config.confirm_clear_overrides": "这会删除云端功能配置覆盖项，不会删除提供商密钥。删除后将回到当前服务实际配置来源：环境变量、config.json 或代码默认值。继续？",
        "config.api_url": "API 地址 (Base URL)",
        "config.runtime_notice_title": "注意：当前执行层仍以原 Smart Search 配置为准",
        "config.runtime_notice_body": "本页展示真实生效配置的来源，同时允许保存云端功能配置覆盖草案。标记为“仅保存”的字段目前不会改变 search/fetch 的实际执行结果，直到服务执行层接入云端配置。",
        "config.effective_runtime": "当前真实生效配置",
        "config.source": "来源",
        "config.stored_only": "仅保存，未接入执行",
        "config.override_note": "这些覆盖会写入云端数据库，但当前 search 执行仍由 service.py 与 config.py 决定。",
        "config.docs_runtime_note": "真实文档搜索当前按 Exa -> Context7 fallback 执行；这里的覆盖项暂不改变执行链。",
        "config.web_search_runtime_note": "真实网页搜索由 zhipu-search 与补充来源逻辑决定；这里的覆盖项暂不改变执行链。",
        "config.fetch_runtime_note": "真实 URL 抓取当前按 Tavily extract -> Firecrawl scrape 执行；这里的覆盖项暂不改变执行链。",
        "config.inherit_runtime": "继承当前运行时配置",
        "config.no_runtime_field": "当前执行层无对应字段",
        "config.optional": "可选",
        "config.search_engine": "搜索引擎",
        # common
        "common.copied": "已复制！",
        "common.error_prefix": "错误：",
        "common.save": "保存",
        "common.saved": "已保存",
    },
    # ------------------------------------------------------------------
    "en": {
        # nav
        "nav.brand": "Smart Search Cloud",
        "nav.sub_brand": "Private Cloud MCP Platform",
        "nav.dashboard": "Dashboard",
        "nav.config_center": "Config Center",
        "nav.monitor": "Service Monitor",
        "nav.tokens": "API Tokens",
        "nav.providers": "Provider Keys",
        "nav.usage": "Usage",
        "nav.audit": "Audit",
        "nav.tasks": "Deep Research",
        "nav.system": "System Settings",
        "nav.settings": "System Settings",
        "nav.logout": "Logout",
        "nav.lang_switch": "中文",
        "nav.group_core": "Core",
        "nav.group_config": "Configuration",
        "nav.group_monitor": "Monitoring",
        "nav.group_system": "System",
        "nav.console": "Console",
        "nav.function_config": "Capability Config",
        "nav.global_audit": "Global Audit",
        "nav.api_docs": "API Docs",
        "nav.resources": "Resources",
        "nav.docs": "Documentation",
        "nav.profile": "Profile",
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
        "providers.title": "Provider Keys",
        "providers.subtitle": "Manage API provider access keys and credentials",
        "providers.credentials": "Credentials",
        "providers.add_credential": "Add Key",
        "providers.provider": "Provider",
        "providers.masked_key": "Key",
        "providers.fingerprint": "Fingerprint",
        "providers.reveal": "Reveal",
        "providers.enabled": "Enabled",
        "providers.enable": "Enable",
        "providers.add_config": "Add Capability Config",
        "providers.capability": "Capability",
        "providers.priority": "Priority",
        "providers.settings": "Settings",
        "providers.edit": "Edit",
        "providers.add_provider_credential": "Add Provider Key",
        "providers.api_key": "API Key",
        "providers.api_secret_optional": "API Secret (optional)",
        "providers.add_provider_config": "Add Capability Config",
        "providers.edit_config": "Edit Capability Config",
        "providers.revealed_credential": "Revealed Credential",
        "providers.close": "Close",
        "providers.show": "Show",
        "providers.required_fields": "Provider and API Key required",
        "providers.credential_created": "Credential created",
        "providers.credential_enabled": "Credential enabled",
        "providers.config_required": "Provider and Capability required",
        "providers.config_created": "Config created",
        "providers.key_revealed": "Key revealed (audit event recorded)",
        "providers.confirm_disable": "Disable this credential?",
        "providers.credential_disabled": "Credential disabled",
        "providers.invalid_settings_json": "Invalid JSON for settings",
        "providers.no_credential": "No credential configured",
        "providers.search_providers": "Search providers...",
        "providers.no_providers": "No provider keys yet. Add a key to get started.",
        "providers.add_capability": "Add Capability",
        "providers.provider_hint": "Select or enter a custom provider identifier",
        "providers.custom": "Custom",
        "providers.custom_provider_name": "Custom provider name",
        "providers.test": "Test",
        "providers.testing": "Testing",
        "providers.test_ok": "Connection OK",
        "providers.test_fail": "Connection failed",
        "providers.remark": "Remark",
        "providers.remark_placeholder": "e.g. Production key",
        "providers.algorithm": "Algorithm",
        "providers.go_to_config": "Go to Capability Config",
        "providers.base_url": "API URL / Base URL",
        "providers.base_url_custom_hint": "Required for custom and OpenAI-compatible providers",
        "providers.base_url_openai_hint": "Optional: custom OpenAI-compatible endpoint",
        "providers.base_url_optional_hint": "Optional: override default API URL",
        # config
        "config.title": "Capability Config",
        "config.subtitle": "Configure channels, models, fallbacks and execution parameters per Smart Search capability",
        "config.clear_overrides": "Clear Overrides",
        "config.save_overrides": "Save Overrides",
        "config.main_search": "Main Search",
        "config.docs_search": "Docs Search",
        "config.web_search": "Web Search",
        "config.web_fetch": "Web Fetch",
        "config.deep_planner": "Deep Planner",
        "config.enable_validation": "Enable Validation",
        "config.primary_channel": "Primary Channel",
        "config.fallback_channel": "FALLBACK Channel",
        "config.select_provider": "Select provider",
        "config.none": "None",
        "config.model": "Model",
        "config.max_results": "Max Results",
        "config.max_items": "Max Items",
        "config.timeout_ms": "Timeout (ms)",
        "config.timeout_s": "Timeout (s)",
        "config.render_js": "JS Render",
        "config.fetch_channel": "Fetch Channel",
        "config.content_limit": "Content Limit",
        "config.format": "Format",
        "config.library_id": "Library ID",
        "config.provider_status": "Provider Status",
        "config.live_status": "Live",
        "config.credentials_only": "Key status",
        "config.manage_credentials": "Manage Keys",
        "config.no_providers_configured": "No providers configured",
        "config.confirm_clear_overrides": "This removes DB-backed capability overrides. Provider keys are not deleted. Runtime will fall back to the currently effective service configuration: environment variables, config.json, or built-in defaults. Continue?",
        "config.api_url": "API URL (Base URL)",
        "config.runtime_notice_title": "Note: runtime still follows original Smart Search configuration",
        "config.runtime_notice_body": "This page shows the currently effective configuration source and lets you save cloud capability override drafts. Fields marked “stored only” do not change actual search/fetch behavior until the service execution layer consumes cloud config.",
        "config.effective_runtime": "Currently Effective Runtime Config",
        "config.source": "Source",
        "config.stored_only": "Stored only, not wired to execution",
        "config.override_note": "These overrides are saved to the cloud database, but search execution is still determined by service.py and config.py.",
        "config.docs_runtime_note": "Real docs search currently runs Exa -> Context7 fallback; these overrides do not change that chain yet.",
        "config.web_search_runtime_note": "Real web search is driven by zhipu-search and supplemental source logic; these overrides do not change that chain yet.",
        "config.fetch_runtime_note": "Real URL fetch currently runs Tavily extract -> Firecrawl scrape; these overrides do not change that chain yet.",
        "config.inherit_runtime": "Inherit current runtime config",
        "config.no_runtime_field": "No current runtime field",
        "config.optional": "Optional",
        "config.search_engine": "Search Engine",
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
