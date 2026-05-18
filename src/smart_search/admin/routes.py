"""Admin WebUI and JSON API routes.

All endpoints require admin scope. Authentication via:
- Bearer token (Authorization header)
- Cookie session (?token=... sets an httponly cookie)
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import HTMLResponse
from jinja2 import Environment, FileSystemLoader, select_autoescape

from ..auth.permissions import ScopeSet
from ..auth.tokens import generate_token, hash_token, token_prefix, verify_token
from ..security.audit import log_audit
from ..security.crypto import decrypt_secret, encrypt_secret, fingerprint_secret, mask_secret

from .schemas import (
    AuditRecord,
    ProviderConfigCreateRequest,
    ProviderConfigResponse,
    ProviderCredentialCreateRequest,
    ProviderCredentialRevealResponse,
    ProviderCredentialResponse,
    SummaryResponse,
    SystemInfoResponse,
    TokenCreateRequest,
    TokenResponse,
    UsageRecord,
)

_logger = logging.getLogger(__name__)

# Jinja2 env (lazy)
_jinja_env: Environment | None = None


def _get_jinja_env() -> Environment:
    global _jinja_env
    if _jinja_env is None:
        templates_dir = Path(__file__).resolve().parent / "templates"
        _jinja_env = Environment(
            loader=FileSystemLoader(str(templates_dir)),
            autoescape=select_autoescape(["html", "xml"]),
        )
    return _jinja_env


def _render(template_name: str, **context: Any) -> str:
    env = _get_jinja_env()
    tmpl = env.get_template(template_name)
    return tmpl.render(**context)


# ---------------------------------------------------------------------------
# Auth dependency
# ---------------------------------------------------------------------------

_ADMIN_COOKIE = "ss_admin_session"


def _require_admin(request: Request) -> tuple[Any, Any]:
    """Validate admin access via Bearer token or cookie.

    Returns (db_session, api_token) on success.
    Raises 401/403 on failure.
    """
    session_factory = getattr(request.app.state, "session_factory", None)
    if session_factory is None:
        raise HTTPException(status_code=500, detail="session_factory not configured")

    token_str: str | None = None

    # 1. Try Bearer header
    auth_header = request.headers.get("authorization", "")
    if auth_header.lower().startswith("bearer "):
        token_str = auth_header[7:].strip()

    # 2. Try cookie
    if token_str is None:
        token_str = request.cookies.get(_ADMIN_COOKIE)

    # 3. Try ?token= query param (set cookie and redirect)
    if token_str is None:
        token_str = request.query_params.get("token")

    if not token_str:
        raise HTTPException(status_code=401, detail="Admin authentication required")

    db_session = session_factory()
    try:
        api_token = verify_token(db_session, token_str)
    except Exception:
        db_session.close()
        raise HTTPException(status_code=401, detail="Token verification failed")

    if api_token is None:
        db_session.close()
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    scope_set = ScopeSet.from_dict(api_token.scopes)
    if not scope_set.allows("admin"):
        db_session.close()
        raise HTTPException(status_code=403, detail="Token lacks admin scope")

    request.state.db_session = db_session
    request.state.api_token = api_token
    return db_session, api_token


def _set_admin_cookie(response: Response, token: str) -> Response:
    """Set httponly cookie for admin session."""
    secure_cookie = os.getenv("SMART_SEARCH_ADMIN_COOKIE_SECURE")
    if secure_cookie is None:
        secure = os.getenv("SMART_SEARCH_ALLOW_INSECURE_DEV_KEYS") != "true"
    else:
        secure = secure_cookie.lower() == "true"
    response.set_cookie(
        key=_ADMIN_COOKIE,
        value=token,
        httponly=True,
        secure=secure,
        samesite="strict",
        max_age=3600 * 8,
        path="/admin",
    )
    return response


# ---------------------------------------------------------------------------
# Router factory
# ---------------------------------------------------------------------------

def create_admin_router() -> APIRouter:
    router = APIRouter(prefix="/admin", tags=["admin"])

    # ------------------------------------------------------------------
    # HTML Pages
    # ------------------------------------------------------------------

    @router.get("/dashboard", response_class=HTMLResponse, name="admin_dashboard")
    async def dashboard_page(request: Request):
        db, api_token = _require_admin(request)
        tenant_id = api_token.tenant_id

        from ..storage.repositories import (
            count_api_tokens, count_active_api_tokens,
            count_provider_credentials, count_active_provider_credentials,
            count_tool_invocations, count_error_invocations,
        )

        summary = SummaryResponse(
            tokens_total=count_api_tokens(db, tenant_id),
            tokens_active=count_active_api_tokens(db, tenant_id),
            providers_total=count_provider_credentials(db, tenant_id),
            providers_active=count_active_provider_credentials(db, tenant_id),
            invocations_total=count_tool_invocations(db, tenant_id),
            invocations_errors=count_error_invocations(db, tenant_id),
        )

        html = _render(
            "dashboard.html",
            summary=summary,
            request=request,
            active_page="dashboard",
        )
        resp = HTMLResponse(html)
        # If token was in query param, set cookie
        qtoken = request.query_params.get("token")
        if qtoken:
            _set_admin_cookie(resp, qtoken)
        return resp

    @router.get("/tokens", response_class=HTMLResponse, name="admin_tokens")
    async def tokens_page(request: Request):
        db, api_token = _require_admin(request)
        tenant_id = api_token.tenant_id

        from ..storage.repositories import list_api_tokens

        tokens = list_api_tokens(db, tenant_id)
        html = _render(
            "tokens.html",
            tokens=tokens,
            request=request,
            active_page="tokens",
        )
        return HTMLResponse(html)

    @router.get("/providers", response_class=HTMLResponse, name="admin_providers")
    async def providers_page(request: Request):
        db, api_token = _require_admin(request)
        tenant_id = api_token.tenant_id

        from ..storage.repositories import list_provider_credentials, list_provider_configs

        credentials = list_provider_credentials(db, tenant_id)
        configs = list_provider_configs(db, tenant_id)
        html = _render(
            "providers.html",
            credentials=credentials,
            configs=configs,
            request=request,
            active_page="providers",
        )
        return HTMLResponse(html)

    @router.get("/usage", response_class=HTMLResponse, name="admin_usage")
    async def usage_page(request: Request):
        db, api_token = _require_admin(request)
        tenant_id = api_token.tenant_id

        from ..storage.repositories import list_tool_invocations

        invocations = list_tool_invocations(db, tenant_id)
        html = _render(
            "usage.html",
            invocations=invocations,
            request=request,
            active_page="usage",
        )
        return HTMLResponse(html)

    @router.get("/audit", response_class=HTMLResponse, name="admin_audit")
    async def audit_page(request: Request):
        db, api_token = _require_admin(request)
        tenant_id = api_token.tenant_id

        from ..storage.repositories import list_audit_events

        events = list_audit_events(db, tenant_id)
        html = _render(
            "audit.html",
            events=events,
            request=request,
            active_page="audit",
        )
        return HTMLResponse(html)

    @router.get("/system", response_class=HTMLResponse, name="admin_system")
    async def system_page(request: Request):
        _require_admin(request)

        engine = getattr(request.app.state, "engine", None)
        db_backend = "sqlite"
        if engine is not None:
            url = str(engine.url)
            if "postgresql" in url or "psycopg" in url:
                db_backend = "postgresql"

        mcp_mounted = getattr(request.app.state, "mcp_mounted", False)

        try:
            import smart_search
            version = getattr(smart_search, "__version__", "0.1.12")
        except Exception:
            version = "0.1.12"

        info = SystemInfoResponse(
            status="ok",
            db_backend=db_backend,
            mcp_mounted=mcp_mounted,
            version=version,
            dependencies=["fastapi", "sqlalchemy", "jinja2", "cryptography", "uvicorn"],
        )

        html = _render(
            "system.html",
            info=info,
            request=request,
            active_page="system",
        )
        return HTMLResponse(html)

    # ------------------------------------------------------------------
    # JSON API
    # ------------------------------------------------------------------

    @router.get("/api/summary", response_model=SummaryResponse)
    async def api_summary(request: Request):
        db, api_token = _require_admin(request)
        tenant_id = api_token.tenant_id

        from ..storage.repositories import (
            count_api_tokens, count_active_api_tokens,
            count_provider_credentials, count_active_provider_credentials,
            count_tool_invocations, count_error_invocations,
        )

        return SummaryResponse(
            tokens_total=count_api_tokens(db, tenant_id),
            tokens_active=count_active_api_tokens(db, tenant_id),
            providers_total=count_provider_credentials(db, tenant_id),
            providers_active=count_active_provider_credentials(db, tenant_id),
            invocations_total=count_tool_invocations(db, tenant_id),
            invocations_errors=count_error_invocations(db, tenant_id),
        )

    @router.get("/api/tokens", response_model=list[TokenResponse])
    async def api_list_tokens(request: Request):
        db, api_token = _require_admin(request)
        tenant_id = api_token.tenant_id

        from ..storage.repositories import list_api_tokens

        tokens = list_api_tokens(db, tenant_id)
        return [
            TokenResponse(
                id=t.id,
                name=t.name,
                token_prefix=t.token_prefix,
                scopes=t.scopes,
                is_active=t.is_active,
                last_used_at=t.last_used_at,
                expires_at=t.expires_at,
                created_at=t.created_at,
            )
            for t in tokens
        ]

    @router.post("/api/tokens", response_model=TokenResponse, status_code=201)
    async def api_create_token(request: Request):
        db, api_token = _require_admin(request)
        tenant_id = api_token.tenant_id
        user_id = api_token.user_id

        body = await request.json()
        create_req = TokenCreateRequest(**body)

        raw_token = generate_token()
        prefix = token_prefix(raw_token)
        token_hash = hash_token(raw_token)

        from ..storage.repositories import store_api_token

        db_token = store_api_token(
            db,
            user_id=user_id,
            tenant_id=tenant_id,
            token_prefix=prefix,
            token_hash=token_hash,
            name=create_req.name,
            scopes=create_req.scopes,
            expires_at=create_req.expires_at,
        )

        log_audit(db, tenant_id=tenant_id, action="token.create",
                  actor_id=user_id, target_type="api_token", target_id=db_token.id)

        return TokenResponse(
            id=db_token.id,
            name=db_token.name,
            token_prefix=db_token.token_prefix,
            scopes=db_token.scopes,
            is_active=db_token.is_active,
            last_used_at=db_token.last_used_at,
            expires_at=db_token.expires_at,
            created_at=db_token.created_at,
            raw_token=raw_token,  # shown only once
        )

    @router.post("/api/tokens/{token_id}/disable")
    async def api_disable_token(token_id: str, request: Request):
        db, api_token = _require_admin(request)
        tenant_id = api_token.tenant_id

        from ..storage.repositories import disable_api_token

        tok = disable_api_token(db, token_id)
        if tok is None:
            raise HTTPException(status_code=404, detail="Token not found")

        log_audit(db, tenant_id=tenant_id, action="token.disable",
                  actor_id=api_token.user_id, target_type="api_token", target_id=token_id)

        return {"ok": True, "id": tok.id, "is_active": False}

    @router.get("/api/providers/credentials", response_model=list[ProviderCredentialResponse])
    async def api_list_credentials(request: Request):
        db, api_token = _require_admin(request)
        tenant_id = api_token.tenant_id

        from ..storage.repositories import list_provider_credentials

        creds = list_provider_credentials(db, tenant_id)
        return [
            ProviderCredentialResponse(
                id=c.id,
                provider=c.provider,
                masked_value=c.masked_value,
                key_fingerprint=c.key_fingerprint,
                algorithm=c.algorithm,
                key_version=c.key_version,
                status=c.status,
                is_active=c.is_active,
                extra=c.extra,
                last_used_at=c.last_used_at,
                created_at=c.created_at,
                updated_at=c.updated_at,
            )
            for c in creds
        ]

    @router.post("/api/providers/credentials", response_model=ProviderCredentialResponse, status_code=201)
    async def api_create_credential(request: Request):
        db, api_token = _require_admin(request)
        tenant_id = api_token.tenant_id

        body = await request.json()
        create_req = ProviderCredentialCreateRequest(**body)

        encrypted_key = encrypt_secret(create_req.api_key)
        encrypted_secret = encrypt_secret(create_req.api_secret) if create_req.api_secret else None
        fp = fingerprint_secret(create_req.api_key)
        masked = mask_secret(create_req.api_key)

        from ..storage.repositories import create_provider_credential

        cred = create_provider_credential(
            db,
            tenant_id=tenant_id,
            provider=create_req.provider,
            encrypted_api_key=encrypted_key,
            encrypted_api_secret=encrypted_secret,
            key_fingerprint=fp,
            masked_value=masked,
            extra=create_req.extra,
        )

        log_audit(db, tenant_id=tenant_id, action="provider_credential.create",
                  actor_id=api_token.user_id, target_type="provider_credential", target_id=cred.id)

        return ProviderCredentialResponse(
            id=cred.id,
            provider=cred.provider,
            masked_value=cred.masked_value,
            key_fingerprint=cred.key_fingerprint,
            algorithm=cred.algorithm,
            key_version=cred.key_version,
            status=cred.status,
            is_active=cred.is_active,
            extra=cred.extra,
            last_used_at=cred.last_used_at,
            created_at=cred.created_at,
            updated_at=cred.updated_at,
        )

    @router.post("/api/providers/credentials/{cred_id}/reveal", response_model=ProviderCredentialRevealResponse)
    async def api_reveal_credential(cred_id: str, request: Request, response: Response):
        db, api_token = _require_admin(request)
        tenant_id = api_token.tenant_id

        from ..storage.repositories import get_provider_credential_by_id

        cred = get_provider_credential_by_id(db, cred_id)
        if cred is None:
            raise HTTPException(status_code=404, detail="Credential not found")

        # Decrypt
        decrypted_key = ""
        if cred.encrypted_api_key:
            decrypted_key = decrypt_secret(cred.encrypted_api_key)

        decrypted_secret = None
        if cred.encrypted_api_secret:
            decrypted_secret = decrypt_secret(cred.encrypted_api_secret)

        log_audit(db, tenant_id=tenant_id, action="provider_key.reveal",
                  actor_id=api_token.user_id,
                  target_type="provider_credential", target_id=cred_id,
                  detail={"provider": cred.provider})

        response.headers["Cache-Control"] = "no-store"
        response.headers["Pragma"] = "no-cache"

        return ProviderCredentialRevealResponse(
            id=cred.id,
            provider=cred.provider,
            api_key=decrypted_key,
            api_secret=decrypted_secret,
        )

    @router.post("/api/providers/credentials/{cred_id}/disable")
    async def api_disable_credential(cred_id: str, request: Request):
        db, api_token = _require_admin(request)
        tenant_id = api_token.tenant_id

        from ..storage.repositories import disable_provider_credential

        cred = disable_provider_credential(db, cred_id)
        if cred is None:
            raise HTTPException(status_code=404, detail="Credential not found")

        log_audit(db, tenant_id=tenant_id, action="provider_credential.disable",
                  actor_id=api_token.user_id,
                  target_type="provider_credential", target_id=cred_id)

        return {"ok": True, "id": cred.id, "is_active": False}

    @router.get("/api/providers/configs", response_model=list[ProviderConfigResponse])
    async def api_list_configs(request: Request):
        db, api_token = _require_admin(request)
        tenant_id = api_token.tenant_id

        from ..storage.repositories import list_provider_configs

        configs = list_provider_configs(db, tenant_id)
        return [
            ProviderConfigResponse(
                id=c.id,
                provider=c.provider,
                capability=c.capability,
                is_enabled=c.is_enabled,
                priority=c.priority,
                settings=c.settings,
                created_at=c.created_at,
                updated_at=c.updated_at,
            )
            for c in configs
        ]

    @router.post("/api/providers/configs", response_model=ProviderConfigResponse, status_code=201)
    async def api_create_config(request: Request):
        db, api_token = _require_admin(request)
        tenant_id = api_token.tenant_id

        body = await request.json()
        create_req = ProviderConfigCreateRequest(**body)

        from ..storage.repositories import create_provider_config

        cfg = create_provider_config(
            db,
            tenant_id=tenant_id,
            provider=create_req.provider,
            capability=create_req.capability,
            is_enabled=create_req.is_enabled,
            priority=create_req.priority,
            settings=create_req.settings,
        )

        log_audit(db, tenant_id=tenant_id, action="provider_config.create",
                  actor_id=api_token.user_id, target_type="provider_config", target_id=cfg.id)

        return ProviderConfigResponse(
            id=cfg.id,
            provider=cfg.provider,
            capability=cfg.capability,
            is_enabled=cfg.is_enabled,
            priority=cfg.priority,
            settings=cfg.settings,
            created_at=cfg.created_at,
            updated_at=cfg.updated_at,
        )

    @router.get("/api/usage", response_model=list[UsageRecord])
    async def api_usage(request: Request):
        db, api_token = _require_admin(request)
        tenant_id = api_token.tenant_id

        from ..storage.repositories import list_tool_invocations

        invocations = list_tool_invocations(db, tenant_id)
        return [
            UsageRecord(
                id=inv.id,
                tool=inv.tool,
                provider=inv.provider,
                is_ok=inv.is_ok,
                error_type=inv.error_type,
                elapsed_ms=inv.elapsed_ms,
                created_at=inv.created_at,
            )
            for inv in invocations
        ]

    @router.get("/api/audit", response_model=list[AuditRecord])
    async def api_audit(request: Request):
        db, api_token = _require_admin(request)
        tenant_id = api_token.tenant_id

        from ..storage.repositories import list_audit_events

        events = list_audit_events(db, tenant_id)
        return [
            AuditRecord(
                id=e.id,
                actor_id=e.actor_id,
                actor_type=e.actor_type,
                action=e.action,
                target_type=e.target_type,
                target_id=e.target_id,
                detail=e.detail,
                created_at=e.created_at,
            )
            for e in events
        ]

    return router
