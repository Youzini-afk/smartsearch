"""Admin WebUI and JSON API routes.

All endpoints require admin scope. Authentication via:
- Bearer token (Authorization header)
- Cookie session (httponly ss_admin_session)
- Password login (SMART_SEARCH_ADMIN_PASSWORD / _PASSWORD_HASH)
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import os
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from jinja2 import Environment, FileSystemLoader, select_autoescape

from ..auth.permissions import ScopeSet
from ..auth.tokens import generate_token, hash_token, token_prefix, verify_token
from ..security.audit import log_audit
from ..security.crypto import decrypt_secret, encrypt_secret, fingerprint_secret, mask_secret

from .i18n import check_lang_redirect, get_i18n_context
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


def _render_html(request: Request, template_name: str, **extra: Any) -> HTMLResponse:
    """Render a template with i18n context injected."""
    i18n = get_i18n_context(request)
    ctx = {**i18n, **extra, "request": request}
    html = _render(template_name, **ctx)
    return HTMLResponse(html)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_ADMIN_COOKIE = "ss_admin_session"


# ---------------------------------------------------------------------------
# Password verification
# ---------------------------------------------------------------------------

def _verify_admin_password(password: str) -> bool:
    """Verify a password against SMART_SEARCH_ADMIN_PASSWORD or _PASSWORD_HASH.

    HASH format: ``sha256:<hex>`` or ``pbkdf2_sha256:<salt>:<hex>``.
    Returns True if the password matches, False otherwise.
    """
    if not password:
        return False

    # Prefer hash over plaintext
    pw_hash = os.getenv("SMART_SEARCH_ADMIN_PASSWORD_HASH")
    if pw_hash:
        if pw_hash.startswith("pbkdf2_sha256:"):
            parts = pw_hash.split(":", 2)
            if len(parts) != 3:
                return False
            _, salt, expected_hex = parts
            dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"),
                                       salt.encode("utf-8"), 260000)
            return hmac.compare_digest(dk.hex(), expected_hex)
        elif pw_hash.startswith("sha256:"):
            expected_hex = pw_hash[len("sha256:"):]
            computed = hashlib.sha256(password.encode("utf-8")).hexdigest()
            return hmac.compare_digest(computed, expected_hex)
        else:
            # Unknown format
            return False

    # Plaintext fallback
    pw_plain = os.getenv("SMART_SEARCH_ADMIN_PASSWORD")
    if pw_plain:
        return hmac.compare_digest(password, pw_plain)

    return False


# ---------------------------------------------------------------------------
# Signed cookie for password-based sessions
# ---------------------------------------------------------------------------

def _sign_session(data: str) -> str:
    """Create a signed session token: data.hmac-sha256."""
    secret = os.getenv("SMART_SEARCH_MASTER_KEY", "dev-key")
    sig = hmac.new(secret.encode("utf-8"), data.encode("utf-8"), hashlib.sha256).hexdigest()[:32]
    return f"{data}.{sig}"


def _verify_session(token: str) -> str | None:
    """Verify a signed session token, returning the data or None."""
    if "." not in token:
        return None
    data, sig = token.rsplit(".", 1)
    secret = os.getenv("SMART_SEARCH_MASTER_KEY", "dev-key")
    expected = hmac.new(secret.encode("utf-8"), data.encode("utf-8"), hashlib.sha256).hexdigest()[:32]
    if hmac.compare_digest(sig, expected):
        return data
    return None


# ---------------------------------------------------------------------------
# Cookie helpers
# ---------------------------------------------------------------------------

def _is_secure_cookie() -> bool:
    secure_env = os.getenv("SMART_SEARCH_ADMIN_COOKIE_SECURE")
    if secure_env is not None:
        return secure_env.lower() == "true"
    return os.getenv("SMART_SEARCH_ALLOW_INSECURE_DEV_KEYS") != "true"


def _set_admin_cookie(response: Response, value: str) -> None:
    """Set httponly admin session cookie."""
    response.set_cookie(
        key=_ADMIN_COOKIE,
        value=value,
        httponly=True,
        secure=_is_secure_cookie(),
        samesite="strict",
        max_age=3600 * 8,
        path="/admin",
    )


def _clear_admin_cookie(response: Response) -> None:
    """Clear the admin session cookie."""
    response.delete_cookie(key=_ADMIN_COOKIE, path="/admin")


def _safe_admin_next(value: Any) -> str:
    """Return a safe same-origin admin redirect target."""
    target = str(value or "/admin/dashboard")
    if not target.startswith("/admin") or target.startswith("//") or "://" in target:
        return "/admin/dashboard"
    return target


# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------

def _try_auth(request: Request) -> tuple[Any, Any] | None:
    """Try to authenticate an admin request. Returns (db_session, api_token) or None.

    Does NOT raise — returns None on auth failure so callers can decide
    what to do (redirect for HTML, 401 for API).

    Sets request.state._auth_forbidden = True when a valid token was found
    but it lacks admin scope, so callers can return 403 instead of 401.
    """
    session_factory = getattr(request.app.state, "session_factory", None)
    if session_factory is None:
        return None

    token_str: str | None = None

    # 1. Bearer header
    auth_header = request.headers.get("authorization", "")
    if auth_header.lower().startswith("bearer "):
        token_str = auth_header[7:].strip()

    # 2. Admin session cookie (could be API token or password-signed session)
    if token_str is None:
        token_str = request.cookies.get(_ADMIN_COOKIE)

    if not token_str:
        return None

    # Check if it's a password-signed session cookie
    session_data = _verify_session(token_str)
    if session_data == "admin":
        # Password-authenticated session. We need a db session but there's no
        # associated api_token. Create a minimal context.
        db_session = session_factory()
        request.state.db_session = db_session
        request.state.api_token = None
        request.state.admin_via_password = True
        # We need tenant_id for queries — use first tenant
        from ..storage.repositories import create_tenant, get_tenant_by_slug
        tenant = get_tenant_by_slug(db_session, "default")
        if tenant is None:
            tenant = create_tenant(db_session, name="Default", slug="default")
            db_session.flush()
        request.state.admin_tenant_id = tenant.id
        return db_session, None

    # API token path
    db_session = session_factory()
    try:
        api_token = verify_token(db_session, token_str)
    except Exception:
        db_session.close()
        return None

    if api_token is None:
        db_session.close()
        return None

    scope_set = ScopeSet.from_dict(api_token.scopes)
    if not scope_set.allows("admin"):
        db_session.close()
        # Distinguish "authenticated but not admin" from "not authenticated"
        request.state._auth_forbidden = True
        return None

    request.state.db_session = db_session
    request.state.api_token = api_token
    request.state.admin_via_password = False
    return db_session, api_token


def _require_admin_api(request: Request) -> tuple[Any, Any]:
    """Validate admin access for JSON API endpoints. Raises 401/403."""
    result = _try_auth(request)
    if result is None:
        if getattr(request.state, "_auth_forbidden", False):
            raise HTTPException(status_code=403, detail="Token lacks admin scope")
        raise HTTPException(status_code=401, detail="Admin authentication required")

    db_session, api_token = result
    if api_token is None:
        # Password-authenticated session is OK for API too
        return db_session, api_token

    return db_session, api_token


def _require_admin_html(request: Request) -> tuple[Any, Any]:
    """Validate admin access for HTML pages. Redirects to login on failure.

    NOTE: This returns a sentinel tuple on failure that the caller must check.
    Alternatively, we use a RedirectResponse directly. Since we can't use
    router middleware, we return (None, None) with a redirect set on request.state.
    """
    result = _try_auth(request)
    if result is None:
        next_url = str(request.url.path)
        request.state._login_redirect = f"/admin/login?next={next_url}"
        return None, None

    db_session, api_token = result
    return db_session, api_token


def _html_or_redirect(request: Request, db: Any, api_token: Any):
    """Check auth result from _require_admin_html. Returns RedirectResponse if not authed."""
    if db is None and api_token is None:
        redirect_url = getattr(request.state, "_login_redirect", "/admin/login")
        return RedirectResponse(url=redirect_url, status_code=302)
    return None


# ---------------------------------------------------------------------------
# Router factory
# ---------------------------------------------------------------------------

def create_admin_router() -> APIRouter:
    router = APIRouter(prefix="/admin", tags=["admin"])

    # ------------------------------------------------------------------
    # Login / Logout
    # ------------------------------------------------------------------

    @router.get("/login", response_class=HTMLResponse, name="admin_login")
    async def login_page(request: Request):
        lang_redir = check_lang_redirect(request)
        if lang_redir:
            return lang_redir
        next_url = _safe_admin_next(request.query_params.get("next", "/admin/dashboard"))
        error = request.query_params.get("error", "")
        return _render_html(request, "login.html", next_url=next_url, error=error)

    @router.post("/login")
    async def login_submit(request: Request):
        form = await request.form()
        login_type = str(form.get("type", "key"))
        next_url = _safe_admin_next(form.get("next", "/admin/dashboard"))
        error_url = f"/admin/login?next={next_url}&error=1"

        if login_type == "password":
            password = str(form.get("password", ""))
            if _verify_admin_password(password):
                # Create signed session cookie
                signed = _sign_session("admin")
                resp = RedirectResponse(url=next_url, status_code=302)
                _set_admin_cookie(resp, signed)
                return resp
            # Failed
            return RedirectResponse(url=error_url, status_code=302)

        # API key login
        key = str(form.get("key", ""))
        if not key:
            return RedirectResponse(url=error_url, status_code=302)

        session_factory = getattr(request.app.state, "session_factory", None)
        if session_factory is None:
            return RedirectResponse(url=error_url, status_code=302)

        db_session = session_factory()
        try:
            api_token = verify_token(db_session, key)
        except Exception:
            db_session.close()
            return RedirectResponse(url=error_url, status_code=302)

        if api_token is None:
            db_session.close()
            return RedirectResponse(url=error_url, status_code=302)

        scope_set = ScopeSet.from_dict(api_token.scopes)
        if not scope_set.allows("admin"):
            db_session.close()
            return RedirectResponse(url=error_url, status_code=302)

        # Success — set cookie with the raw token value so _try_auth can verify it
        db_session.close()
        resp = RedirectResponse(url=next_url, status_code=302)
        _set_admin_cookie(resp, key)
        return resp

    @router.get("/logout", name="admin_logout")
    async def logout(request: Request):
        resp = RedirectResponse(url="/admin/login", status_code=302)
        _clear_admin_cookie(resp)
        return resp

    # ------------------------------------------------------------------
    # /admin bare → redirect to dashboard or login
    # ------------------------------------------------------------------

    @router.get("", response_class=HTMLResponse)
    async def admin_root(request: Request):
        result = _try_auth(request)
        if result is not None:
            return RedirectResponse(url="/admin/dashboard", status_code=302)
        return RedirectResponse(url="/admin/login", status_code=302)

    # ------------------------------------------------------------------
    # HTML Pages (all use _require_admin_html → 302 to login)
    # ------------------------------------------------------------------

    @router.get("/dashboard", response_class=HTMLResponse, name="admin_dashboard")
    async def dashboard_page(request: Request):
        lang_redir = check_lang_redirect(request)
        if lang_redir:
            return lang_redir
        db, api_token = _require_admin_html(request)
        redir = _html_or_redirect(request, db, api_token)
        if redir:
            return redir
        tenant_id = (api_token.tenant_id if api_token
                     else getattr(request.state, "admin_tenant_id", ""))

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

        return _render_html(request, "dashboard.html", summary=summary, active_page="dashboard")

    @router.get("/tokens", response_class=HTMLResponse, name="admin_tokens")
    async def tokens_page(request: Request):
        lang_redir = check_lang_redirect(request)
        if lang_redir:
            return lang_redir
        db, api_token = _require_admin_html(request)
        redir = _html_or_redirect(request, db, api_token)
        if redir:
            return redir
        tenant_id = (api_token.tenant_id if api_token
                     else getattr(request.state, "admin_tenant_id", ""))

        from ..storage.repositories import list_api_tokens

        tokens = list_api_tokens(db, tenant_id)
        return _render_html(request, "tokens.html", tokens=tokens, active_page="tokens")

    @router.get("/providers", response_class=HTMLResponse, name="admin_providers")
    async def providers_page(request: Request):
        lang_redir = check_lang_redirect(request)
        if lang_redir:
            return lang_redir
        db, api_token = _require_admin_html(request)
        redir = _html_or_redirect(request, db, api_token)
        if redir:
            return redir
        tenant_id = (api_token.tenant_id if api_token
                     else getattr(request.state, "admin_tenant_id", ""))

        from ..storage.repositories import list_provider_credentials, list_provider_configs

        credentials = list_provider_credentials(db, tenant_id)
        configs = list_provider_configs(db, tenant_id)
        return _render_html(request, "providers.html", credentials=credentials, configs=configs, active_page="providers")

    @router.get("/usage", response_class=HTMLResponse, name="admin_usage")
    async def usage_page(request: Request):
        lang_redir = check_lang_redirect(request)
        if lang_redir:
            return lang_redir
        db, api_token = _require_admin_html(request)
        redir = _html_or_redirect(request, db, api_token)
        if redir:
            return redir
        tenant_id = (api_token.tenant_id if api_token
                     else getattr(request.state, "admin_tenant_id", ""))

        from ..storage.repositories import list_tool_invocations

        invocations = list_tool_invocations(db, tenant_id)
        return _render_html(request, "usage.html", invocations=invocations, active_page="usage")

    @router.get("/audit", response_class=HTMLResponse, name="admin_audit")
    async def audit_page(request: Request):
        lang_redir = check_lang_redirect(request)
        if lang_redir:
            return lang_redir
        db, api_token = _require_admin_html(request)
        redir = _html_or_redirect(request, db, api_token)
        if redir:
            return redir
        tenant_id = (api_token.tenant_id if api_token
                     else getattr(request.state, "admin_tenant_id", ""))

        from ..storage.repositories import list_audit_events

        events = list_audit_events(db, tenant_id)
        return _render_html(request, "audit.html", events=events, active_page="audit")

    @router.get("/tasks", response_class=HTMLResponse, name="admin_tasks")
    async def tasks_page(request: Request):
        lang_redir = check_lang_redirect(request)
        if lang_redir:
            return lang_redir
        db, api_token = _require_admin_html(request)
        redir = _html_or_redirect(request, db, api_token)
        if redir:
            return redir
        tenant_id = (api_token.tenant_id if api_token
                     else getattr(request.state, "admin_tenant_id", ""))

        from ..storage.repositories import list_task_runs

        tasks = list_task_runs(db, tenant_id)
        return _render_html(request, "tasks.html", tasks=tasks, active_page="tasks")

    @router.get("/system", response_class=HTMLResponse, name="admin_system")
    async def system_page(request: Request):
        lang_redir = check_lang_redirect(request)
        if lang_redir:
            return lang_redir
        db, api_token = _require_admin_html(request)
        redir = _html_or_redirect(request, db, api_token)
        if redir:
            return redir

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

        return _render_html(request, "system.html", info=info, active_page="system")

    # ------------------------------------------------------------------
    # JSON API (all use _require_admin_api → 401/403 JSON)
    # ------------------------------------------------------------------

    @router.get("/api/summary", response_model=SummaryResponse)
    async def api_summary(request: Request):
        db, api_token = _require_admin_api(request)
        tenant_id = (api_token.tenant_id if api_token
                     else getattr(request.state, "admin_tenant_id", ""))

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
        db, api_token = _require_admin_api(request)
        tenant_id = (api_token.tenant_id if api_token
                     else getattr(request.state, "admin_tenant_id", ""))

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
        db, api_token = _require_admin_api(request)
        tenant_id = (api_token.tenant_id if api_token
                     else getattr(request.state, "admin_tenant_id", ""))
        user_id = api_token.user_id if api_token else "admin-password-session"

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
        db, api_token = _require_admin_api(request)
        tenant_id = (api_token.tenant_id if api_token
                     else getattr(request.state, "admin_tenant_id", ""))

        from ..storage.repositories import disable_api_token

        tok = disable_api_token(db, token_id)
        if tok is None:
            raise HTTPException(status_code=404, detail="Token not found")

        log_audit(db, tenant_id=tenant_id, action="token.disable",
                  actor_id=api_token.user_id if api_token else "admin-password-session",
                  target_type="api_token", target_id=token_id)

        return {"ok": True, "id": tok.id, "is_active": False}

    @router.get("/api/providers/credentials", response_model=list[ProviderCredentialResponse])
    async def api_list_credentials(request: Request):
        db, api_token = _require_admin_api(request)
        tenant_id = (api_token.tenant_id if api_token
                     else getattr(request.state, "admin_tenant_id", ""))

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
        db, api_token = _require_admin_api(request)
        tenant_id = (api_token.tenant_id if api_token
                     else getattr(request.state, "admin_tenant_id", ""))

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
                  actor_id=api_token.user_id if api_token else "admin-password-session",
                  target_type="provider_credential", target_id=cred.id)

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
        db, api_token = _require_admin_api(request)
        tenant_id = (api_token.tenant_id if api_token
                     else getattr(request.state, "admin_tenant_id", ""))

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
                  actor_id=api_token.user_id if api_token else "admin-password-session",
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
        db, api_token = _require_admin_api(request)
        tenant_id = (api_token.tenant_id if api_token
                     else getattr(request.state, "admin_tenant_id", ""))

        from ..storage.repositories import disable_provider_credential

        cred = disable_provider_credential(db, cred_id)
        if cred is None:
            raise HTTPException(status_code=404, detail="Credential not found")

        log_audit(db, tenant_id=tenant_id, action="provider_credential.disable",
                  actor_id=api_token.user_id if api_token else "admin-password-session",
                  target_type="provider_credential", target_id=cred_id)

        return {"ok": True, "id": cred.id, "is_active": False}

    @router.get("/api/providers/configs", response_model=list[ProviderConfigResponse])
    async def api_list_configs(request: Request):
        db, api_token = _require_admin_api(request)
        tenant_id = (api_token.tenant_id if api_token
                     else getattr(request.state, "admin_tenant_id", ""))

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
        db, api_token = _require_admin_api(request)
        tenant_id = (api_token.tenant_id if api_token
                     else getattr(request.state, "admin_tenant_id", ""))

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
                  actor_id=api_token.user_id if api_token else "admin-password-session",
                  target_type="provider_config", target_id=cfg.id)

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
        db, api_token = _require_admin_api(request)
        tenant_id = (api_token.tenant_id if api_token
                     else getattr(request.state, "admin_tenant_id", ""))

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
        db, api_token = _require_admin_api(request)
        tenant_id = (api_token.tenant_id if api_token
                     else getattr(request.state, "admin_tenant_id", ""))

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

    # ------------------------------------------------------------------
    # Task admin API
    # ------------------------------------------------------------------

    @router.get("/api/tasks")
    async def api_list_tasks(request: Request):
        db, api_token = _require_admin_api(request)
        tenant_id = (api_token.tenant_id if api_token
                     else getattr(request.state, "admin_tenant_id", ""))

        from ..storage.repositories import list_task_runs

        tasks = list_task_runs(db, tenant_id)
        return [
            {
                "id": t.id,
                "task_type": t.task_type,
                "status": t.status,
                "topic": t.topic,
                "created_at": t.created_at.isoformat() if t.created_at else None,
                "updated_at": t.updated_at.isoformat() if t.updated_at else None,
            }
            for t in tasks
        ]

    @router.get("/api/tasks/{task_id}/detail")
    async def api_task_detail(task_id: str, request: Request):
        db, api_token = _require_admin_api(request)
        tenant_id = (api_token.tenant_id if api_token
                     else getattr(request.state, "admin_tenant_id", ""))

        from ..storage.repositories import get_task_run, list_task_nodes, list_task_events

        tr = get_task_run(db, task_id)
        if tr is None or tr.tenant_id != tenant_id:
            raise HTTPException(status_code=404, detail="Task not found")

        nodes = list_task_nodes(db, task_id)
        events = list_task_events(db, task_id)
        return {
            "id": tr.id,
            "status": tr.status,
            "topic": tr.topic,
            "task_type": tr.task_type,
            "error": tr.error,
            "result": tr.result,
            "nodes": [
                {
                    "id": n.id,
                    "name": n.name,
                    "node_type": n.node_type,
                    "status": n.status,
                    "error": n.error,
                }
                for n in nodes
            ],
            "events": [
                {
                    "id": e.id,
                    "node_id": e.node_id,
                    "event_type": e.event_type,
                    "message": e.message,
                    "created_at": e.created_at.isoformat() if e.created_at else None,
                }
                for e in events
            ],
            "created_at": tr.created_at.isoformat() if tr.created_at else None,
        }

    @router.post("/api/tasks/{task_id}/pause")
    async def api_pause_task(task_id: str, request: Request):
        db, api_token = _require_admin_api(request)

        from ..storage.repositories import get_task_run
        from ..tasks.queue import DBBackedQueue

        tr = get_task_run(db, task_id)
        if tr is None or tr.tenant_id != (api_token.tenant_id if api_token
                                           else getattr(request.state, "admin_tenant_id", "")):
            raise HTTPException(status_code=404, detail="Task not found")

        queue = DBBackedQueue(db)
        queue.pause_task(task_id)
        return {"task_id": task_id, "status": "paused"}

    @router.post("/api/tasks/{task_id}/resume")
    async def api_resume_task(task_id: str, request: Request):
        db, api_token = _require_admin_api(request)

        from ..storage.repositories import get_task_run
        from ..tasks.queue import DBBackedQueue

        tr = get_task_run(db, task_id)
        if tr is None or tr.tenant_id != (api_token.tenant_id if api_token
                                           else getattr(request.state, "admin_tenant_id", "")):
            raise HTTPException(status_code=404, detail="Task not found")

        queue = DBBackedQueue(db)
        queue.resume_task(task_id)
        return {"task_id": task_id, "status": "queued"}

    @router.post("/api/tasks/{task_id}/cancel")
    async def api_cancel_task(task_id: str, request: Request):
        db, api_token = _require_admin_api(request)

        from ..storage.repositories import get_task_run
        from ..tasks.queue import DBBackedQueue

        tr = get_task_run(db, task_id)
        if tr is None or tr.tenant_id != (api_token.tenant_id if api_token
                                           else getattr(request.state, "admin_tenant_id", "")):
            raise HTTPException(status_code=404, detail="Task not found")

        queue = DBBackedQueue(db)
        queue.cancel_task(task_id)
        return {"task_id": task_id, "status": "cancelled"}

    @router.post("/api/tasks/nodes/{node_id}/retry")
    async def api_retry_node(node_id: str, request: Request):
        db, api_token = _require_admin_api(request)

        from ..storage.repositories import get_task_node, retry_node as repo_retry_node, get_task_run

        node = get_task_node(db, node_id)
        if node is None:
            raise HTTPException(status_code=404, detail="Node not found")
        tr = get_task_run(db, node.task_run_id)
        if tr is None or tr.tenant_id != (api_token.tenant_id if api_token
                                           else getattr(request.state, "admin_tenant_id", "")):
            raise HTTPException(status_code=404, detail="Node not found")

        updated = repo_retry_node(db, node_id)
        return {"node_id": node_id, "status": updated.status if updated else "error"}

    @router.post("/api/tasks/nodes/{node_id}/redo")
    async def api_redo_node(node_id: str, request: Request):
        db, api_token = _require_admin_api(request)

        from ..storage.repositories import (
            get_task_node, redo_node_mark_downstream_stale, get_task_run,
        )

        node = get_task_node(db, node_id)
        if node is None:
            raise HTTPException(status_code=404, detail="Node not found")
        tr = get_task_run(db, node.task_run_id)
        if tr is None or tr.tenant_id != (api_token.tenant_id if api_token
                                           else getattr(request.state, "admin_tenant_id", "")):
            raise HTTPException(status_code=404, detail="Node not found")

        affected = redo_node_mark_downstream_stale(db, node_id)
        return {"node_id": node_id, "affected_nodes": affected}

    return router
