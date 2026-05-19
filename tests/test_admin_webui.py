"""Admin WebUI and API tests.

Uses TestClient + SQLite tmp. No network.
Covers: admin token access, non-admin 403, token create (raw only in response),
provider credential create+reveal+audit, disable token/provider, summary/usage/audit pages,
login page, password auth, redirect flows, logout, i18n.
"""

from __future__ import annotations

import hashlib
import os
import sys
from pathlib import Path

import pytest

# Ensure src is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _isolate_env(monkeypatch, tmp_path):
    """Isolate config and provide stable crypto keys."""
    from smart_search.config import Config

    cfg = Config()
    monkeypatch.setattr(cfg, "_config_file", tmp_path / "config.json")
    monkeypatch.setattr(cfg, "_config_dir_source", "override")
    monkeypatch.setattr(cfg, "_cached_model", None)
    for key in cfg._CONFIG_KEYS:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.delenv("SMART_SEARCH_CONFIG_DIR", raising=False)
    monkeypatch.setenv("SMART_SEARCH_MINIMUM_PROFILE", "off")

    # Clear security caches
    from smart_search.security.crypto import reset_master_fernet
    reset_master_fernet()

    # Provide stable keys
    monkeypatch.setenv("SMART_SEARCH_MASTER_KEY", "test-master-key-for-admin-tests")
    monkeypatch.setenv("SMART_SEARCH_TOKEN_SECRET", "test-token-secret-for-admin")
    monkeypatch.setenv("SMART_SEARCH_ALLOW_INSECURE_DEV_KEYS", "true")
    monkeypatch.setenv("SMART_SEARCH_FINGERPRINT_SECRET", "test-fp-secret")
    # Admin password for password-login tests
    monkeypatch.setenv("SMART_SEARCH_ADMIN_PASSWORD", "test-admin-pw")


@pytest.fixture()
def app_and_client(tmp_path):
    """Create a FastAPI TestClient with a temp SQLite DB."""
    from sqlalchemy import create_engine
    from smart_search.storage.models import Base
    from smart_search.storage.db import create_session_factory, init_db
    from smart_search.server.app import create_app

    db_path = tmp_path / "admin-test.db"
    url = f"sqlite:///{db_path}"
    engine = create_engine(url, connect_args={"check_same_thread": False})
    init_db(engine)
    session_factory = create_session_factory(engine)

    app = create_app(engine=engine, session_factory=session_factory)

    from starlette.testclient import TestClient
    client = TestClient(app)

    yield app, client, engine, session_factory

    Base.metadata.drop_all(bind=engine)
    engine.dispose()


@pytest.fixture()
def admin_token(app_and_client):
    """Create an admin token and return (raw_token_string, api_token_obj, tenant, user)."""
    _, client, engine, session_factory = app_and_client

    from smart_search.auth.tokens import generate_token, hash_token, token_prefix
    from smart_search.storage.repositories import (
        create_tenant, create_user, add_membership, store_api_token,
    )

    sess = session_factory()
    tenant = create_tenant(sess, name="TestOrg", slug="testorg")
    user = create_user(sess, email="admin@test.com", display_name="Admin")
    add_membership(sess, tenant_id=tenant.id, user_id=user.id, role="admin")
    sess.commit()

    raw = generate_token()
    prefix = token_prefix(raw)
    token_hash = hash_token(raw)

    db_token = store_api_token(
        sess,
        user_id=user.id,
        tenant_id=tenant.id,
        token_prefix=prefix,
        token_hash=token_hash,
        name="admin-token",
        scopes={"permissions": ["admin"]},
    )
    sess.commit()
    sess.close()

    return raw, db_token, tenant, user


@pytest.fixture()
def non_admin_token(app_and_client):
    """Create a non-admin token and return the raw token string."""
    _, client, engine, session_factory = app_and_client

    from smart_search.auth.tokens import generate_token, hash_token, token_prefix
    from smart_search.storage.repositories import (
        create_tenant, create_user, store_api_token,
    )

    sess = session_factory()
    tenant = create_tenant(sess, name="NonAdminOrg", slug="nonadmin")
    user = create_user(sess, email="user@test.com")
    raw = generate_token()
    prefix = token_prefix(raw)
    token_hash = hash_token(raw)

    store_api_token(
        sess,
        user_id=user.id,
        tenant_id=tenant.id,
        token_prefix=prefix,
        token_hash=token_hash,
        name="readonly-token",
        scopes={"permissions": ["search:read"]},
    )
    sess.commit()
    sess.close()

    return raw


# ---------------------------------------------------------------------------
# Tests: Redirect flows
# ---------------------------------------------------------------------------

class TestRedirectFlows:
    def test_root_redirects_to_admin(self, app_and_client):
        """GET / redirects to /admin (which then redirects to login/dashboard)."""
        _, client, _, _ = app_and_client
        resp = client.get("/", follow_redirects=False)
        assert resp.status_code == 302
        assert "/admin" in resp.headers["location"]

    def test_admin_root_unauth_redirects_login(self, app_and_client):
        """GET /admin without auth redirects to /admin/login."""
        _, client, _, _ = app_and_client
        resp = client.get("/admin", follow_redirects=False)
        assert resp.status_code == 302
        assert "/admin/login" in resp.headers["location"]

    def test_admin_root_auth_redirects_dashboard(self, app_and_client, admin_token):
        """GET /admin with auth redirects to /admin/dashboard."""
        _, client, _, _ = app_and_client
        raw, _, _, _ = admin_token
        resp = client.get("/admin", headers={"Authorization": f"Bearer {raw}"}, follow_redirects=False)
        assert resp.status_code == 302
        assert "/admin/dashboard" in resp.headers["location"]

    def test_dashboard_unauth_redirects_login(self, app_and_client):
        """GET /admin/dashboard without auth redirects to login with next param."""
        _, client, _, _ = app_and_client
        resp = client.get("/admin/dashboard", follow_redirects=False)
        assert resp.status_code == 302
        location = resp.headers["location"]
        assert "/admin/login" in location
        assert "next=" in location

    def test_api_summary_unauth_remains_401(self, app_and_client):
        """GET /admin/api/summary without auth returns 401 JSON, not redirect."""
        _, client, _, _ = app_and_client
        resp = client.get("/admin/api/summary")
        assert resp.status_code == 401
        assert resp.headers.get("content-type", "").startswith("application/json")


# ---------------------------------------------------------------------------
# Tests: Login page and flows
# ---------------------------------------------------------------------------

class TestLoginPage:
    def test_login_page_renders(self, app_and_client):
        """GET /admin/login shows the login form."""
        _, client, _, _ = app_and_client
        resp = client.get("/admin/login")
        assert resp.status_code == 200
        # Default locale is zh-CN
        assert "管理后台" in resp.text or "Smart Search Admin" in resp.text
        assert "API" in resp.text
        assert "密码" in resp.text or "Password" in resp.text

    def test_key_login_sets_cookie_redirects_dashboard(self, app_and_client, admin_token):
        """POST /admin/login with valid admin key sets cookie and redirects."""
        _, client, _, _ = app_and_client
        raw, _, _, _ = admin_token
        resp = client.post("/admin/login", data={"type": "key", "key": raw, "next": "/admin/dashboard"},
                           follow_redirects=False)
        assert resp.status_code == 302
        assert "/admin/dashboard" in resp.headers["location"]
        # Cookie should be set
        set_cookie = resp.headers.get("set-cookie", "")
        assert "ss_admin_session" in set_cookie

    def test_key_login_non_admin_fails(self, app_and_client, non_admin_token):
        """POST /admin/login with non-admin key redirects back with error."""
        _, client, _, _ = app_and_client
        resp = client.post("/admin/login", data={"type": "key", "key": non_admin_token, "next": "/admin/dashboard"},
                           follow_redirects=False)
        assert resp.status_code == 302
        assert "error=1" in resp.headers["location"]

    def test_key_login_invalid_key_fails(self, app_and_client):
        """POST /admin/login with invalid key redirects back with error."""
        _, client, _, _ = app_and_client
        resp = client.post("/admin/login", data={"type": "key", "key": "sk_live_invalid", "next": "/admin/dashboard"},
                           follow_redirects=False)
        assert resp.status_code == 302
        assert "error=1" in resp.headers["location"]

    def test_password_login_sets_cookie(self, app_and_client):
        """POST /admin/login with correct password sets cookie and redirects."""
        _, client, _, _ = app_and_client
        resp = client.post("/admin/login",
                           data={"type": "password", "password": "test-admin-pw", "next": "/admin/dashboard"},
                           follow_redirects=False)
        assert resp.status_code == 302
        assert "/admin/dashboard" in resp.headers["location"]
        set_cookie = resp.headers.get("set-cookie", "")
        assert "ss_admin_session" in set_cookie

    def test_password_login_wrong_password_fails(self, app_and_client):
        """POST /admin/login with wrong password redirects back with error."""
        _, client, _, _ = app_and_client
        resp = client.post("/admin/login",
                           data={"type": "password", "password": "wrong-pw", "next": "/admin/dashboard"},
                           follow_redirects=False)
        assert resp.status_code == 302
        assert "error=1" in resp.headers["location"]

    def test_password_login_sha256_hash(self, app_and_client, monkeypatch):
        """POST /admin/login with SMART_SEARCH_ADMIN_PASSWORD_HASH=sha256:... works."""
        _, client, _, _ = app_and_client
        pw = "hashed-password"
        sha = hashlib.sha256(pw.encode("utf-8")).hexdigest()
        monkeypatch.setenv("SMART_SEARCH_ADMIN_PASSWORD_HASH", f"sha256:{sha}")
        monkeypatch.delenv("SMART_SEARCH_ADMIN_PASSWORD", raising=False)

        resp = client.post("/admin/login",
                           data={"type": "password", "password": pw, "next": "/admin/dashboard"},
                           follow_redirects=False)
        assert resp.status_code == 302
        assert "/admin/dashboard" in resp.headers["location"]


# ---------------------------------------------------------------------------
# Tests: Logout
# ---------------------------------------------------------------------------

class TestLogout:
    def test_logout_clears_cookie(self, app_and_client, admin_token):
        """GET /admin/logout clears the cookie and redirects to login."""
        _, client, _, _ = app_and_client
        raw, _, _, _ = admin_token
        resp = client.get("/admin/logout", follow_redirects=False)
        assert resp.status_code == 302
        assert "/admin/login" in resp.headers["location"]
        # Check that cookie is cleared (set-cookie with empty value or Max-Age=0)
        set_cookie = resp.headers.get("set-cookie", "")
        assert "ss_admin_session" in set_cookie


# ---------------------------------------------------------------------------
# Tests: Admin auth (Bearer / cookie)
# ---------------------------------------------------------------------------

class TestAdminAuth:
    def test_admin_can_access_dashboard(self, app_and_client, admin_token):
        _, client, _, _ = app_and_client
        raw, _, _, _ = admin_token
        resp = client.get("/admin/dashboard", headers={"Authorization": f"Bearer {raw}"})
        assert resp.status_code == 200
        # Page content should have dashboard title in either language
        assert "仪表盘" in resp.text or "Dashboard" in resp.text

    def test_non_admin_gets_403_via_api(self, app_and_client, non_admin_token):
        _, client, _, _ = app_and_client
        resp = client.get("/admin/api/summary", headers={"Authorization": f"Bearer {non_admin_token}"})
        assert resp.status_code == 403

    def test_non_admin_html_redirects_login(self, app_and_client, non_admin_token):
        """Non-admin token on HTML page should redirect to login (not 403)."""
        _, client, _, _ = app_and_client
        resp = client.get("/admin/dashboard", headers={"Authorization": f"Bearer {non_admin_token}"},
                          follow_redirects=False)
        assert resp.status_code == 302
        assert "/admin/login" in resp.headers["location"]

    def test_no_auth_api_returns_401(self, app_and_client):
        _, client, _, _ = app_and_client
        resp = client.get("/admin/api/summary")
        assert resp.status_code == 401

    def test_cookie_auth(self, app_and_client, admin_token):
        _, client, _, _ = app_and_client
        raw, _, _, _ = admin_token
        # Login via form sets cookie, then access dashboard
        client.post("/admin/login", data={"type": "key", "key": raw, "next": "/admin/dashboard"})
        resp = client.get("/admin/dashboard")
        assert resp.status_code == 200
        assert "仪表盘" in resp.text or "Dashboard" in resp.text


# ---------------------------------------------------------------------------
# Tests: Token API
# ---------------------------------------------------------------------------

class TestAdminTokenAPI:
    def test_create_token_raw_shown_once(self, app_and_client, admin_token):
        _, client, _, _ = app_and_client
        raw, _, tenant, user = admin_token

        resp = client.post(
            "/admin/api/tokens",
            json={"name": "new-test-token", "scopes": {"permissions": ["search:read"]}},
            headers={"Authorization": f"Bearer {raw}"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert "raw_token" in data
        assert data["raw_token"] is not None
        assert data["raw_token"].startswith("sk_live_")
        assert data["name"] == "new-test-token"
        assert "token_prefix" in data
        assert data["token_prefix"] != data["raw_token"]

    def test_disable_token(self, app_and_client, admin_token):
        _, client, _, _ = app_and_client
        raw, _, _, _ = admin_token

        resp = client.post(
            "/admin/api/tokens",
            json={"name": "to-disable", "scopes": {"permissions": ["search:read"]}},
            headers={"Authorization": f"Bearer {raw}"},
        )
        token_id = resp.json()["id"]

        resp = client.post(
            f"/admin/api/tokens/{token_id}/disable",
            headers={"Authorization": f"Bearer {raw}"},
        )
        assert resp.status_code == 200
        assert resp.json()["is_active"] is False


# ---------------------------------------------------------------------------
# Tests: Provider API
# ---------------------------------------------------------------------------

class TestAdminProviderAPI:
    def test_create_credential_and_reveal(self, app_and_client, admin_token):
        _, client, _, _ = app_and_client
        raw, _, _, _ = admin_token

        resp = client.post(
            "/admin/api/providers/credentials",
            json={"provider": "xai-responses", "api_key": "sk-xai-test-secret-key"},
            headers={"Authorization": f"Bearer {raw}"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["provider"] == "xai-responses"
        assert data["masked_value"]
        assert "sk-xai" not in data["masked_value"]
        cred_id = data["id"]

        resp = client.post(
            f"/admin/api/providers/credentials/{cred_id}/reveal",
            headers={"Authorization": f"Bearer {raw}"},
        )
        assert resp.status_code == 200
        assert resp.headers.get("cache-control") == "no-store"
        reveal = resp.json()
        assert reveal["api_key"] == "sk-xai-test-secret-key"

        resp = client.get("/admin/api/audit", headers={"Authorization": f"Bearer {raw}"})
        events = resp.json()
        reveal_events = [e for e in events if e["action"] == "provider_key.reveal"]
        assert len(reveal_events) >= 1

    def test_disable_credential(self, app_and_client, admin_token):
        _, client, _, _ = app_and_client
        raw, _, _, _ = admin_token

        resp = client.post(
            "/admin/api/providers/credentials",
            json={"provider": "exa", "api_key": "sk-exa-key"},
            headers={"Authorization": f"Bearer {raw}"},
        )
        cred_id = resp.json()["id"]

        resp = client.post(
            f"/admin/api/providers/credentials/{cred_id}/disable",
            headers={"Authorization": f"Bearer {raw}"},
        )
        assert resp.status_code == 200
        assert resp.json()["is_active"] is False

    def test_create_provider_config(self, app_and_client, admin_token):
        _, client, _, _ = app_and_client
        raw, _, _, _ = admin_token

        resp = client.post(
            "/admin/api/providers/configs",
            json={"provider": "xai-responses", "capability": "main_search", "priority": 10, "settings": {"model": "grok-3"}},
            headers={"Authorization": f"Bearer {raw}"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["provider"] == "xai-responses"
        assert data["capability"] == "main_search"
        assert data["priority"] == 10


# ---------------------------------------------------------------------------
# Tests: Summary / Usage / Audit pages and API
# ---------------------------------------------------------------------------

class TestAdminSummaryUsageAudit:
    def test_summary_api(self, app_and_client, admin_token):
        _, client, _, _ = app_and_client
        raw, _, _, _ = admin_token

        resp = client.get("/admin/api/summary", headers={"Authorization": f"Bearer {raw}"})
        assert resp.status_code == 200
        data = resp.json()
        assert "tokens_total" in data
        assert "tokens_active" in data
        assert "providers_total" in data
        assert "invocations_total" in data
        assert "invocations_errors" in data
        # New analytics field
        assert "analytics" in data
        analytics = data["analytics"]
        assert "total" in analytics
        assert "errors" in analytics
        assert "success_rate" in analytics
        assert "avg_elapsed_ms" in analytics
        assert "by_tool" in analytics
        assert "by_provider" in analytics
        assert "top_errors" in analytics
        assert "trend" in analytics

    def test_summary_api_period(self, app_and_client, admin_token):
        _, client, _, _ = app_and_client
        raw, _, _, _ = admin_token

        for period in ("24h", "7d", "30d"):
            resp = client.get(f"/admin/api/summary?period={period}", headers={"Authorization": f"Bearer {raw}"})
            assert resp.status_code == 200
            data = resp.json()
            assert "analytics" in data

    def test_usage_page(self, app_and_client, admin_token):
        _, client, _, _ = app_and_client
        raw, _, _, _ = admin_token

        resp = client.get("/admin/usage", headers={"Authorization": f"Bearer {raw}"})
        assert resp.status_code == 200
        assert "工具调用" in resp.text or "Invocations" in resp.text

    def test_audit_page(self, app_and_client, admin_token):
        _, client, _, _ = app_and_client
        raw, _, _, _ = admin_token

        resp = client.get("/admin/audit", headers={"Authorization": f"Bearer {raw}"})
        assert resp.status_code == 200
        assert "审计事件" in resp.text or "Audit" in resp.text

    def test_usage_api(self, app_and_client, admin_token):
        _, client, _, _ = app_and_client
        raw, _, _, _ = admin_token

        resp = client.get("/admin/api/usage", headers={"Authorization": f"Bearer {raw}"})
        assert resp.status_code == 200

    def test_audit_api(self, app_and_client, admin_token):
        _, client, _, _ = app_and_client
        raw, _, _, _ = admin_token

        resp = client.get("/admin/api/audit", headers={"Authorization": f"Bearer {raw}"})
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Tests: System / Tokens / Providers pages
# ---------------------------------------------------------------------------

class TestAdminSystemPage:
    def test_system_page(self, app_and_client, admin_token):
        _, client, _, _ = app_and_client
        raw, _, _, _ = admin_token

        resp = client.get("/admin/system", headers={"Authorization": f"Bearer {raw}"})
        assert resp.status_code == 200
        assert "系统" in resp.text or "System" in resp.text


class TestAdminTokensPage:
    def test_tokens_page(self, app_and_client, admin_token):
        _, client, _, _ = app_and_client
        raw, _, _, _ = admin_token

        resp = client.get("/admin/tokens", headers={"Authorization": f"Bearer {raw}"})
        assert resp.status_code == 200
        assert "令牌" in resp.text or "Tokens" in resp.text


class TestAdminProvidersPage:
    def test_providers_page(self, app_and_client, admin_token):
        _, client, _, _ = app_and_client
        raw, _, _, _ = admin_token

        resp = client.get("/admin/providers", headers={"Authorization": f"Bearer {raw}"})
        assert resp.status_code == 200
        assert "提供者" in resp.text or "Providers" in resp.text


# ---------------------------------------------------------------------------
# Tests: Password-authenticated session
# ---------------------------------------------------------------------------

class TestPasswordSession:
    def test_password_session_can_access_dashboard(self, app_and_client):
        """After password login, dashboard is accessible."""
        _, client, _, _ = app_and_client
        # Login
        client.post("/admin/login",
                    data={"type": "password", "password": "test-admin-pw", "next": "/admin/dashboard"})
        # Access dashboard
        resp = client.get("/admin/dashboard")
        assert resp.status_code == 200
        assert "仪表盘" in resp.text or "Dashboard" in resp.text

    def test_password_session_can_access_api(self, app_and_client):
        """After password login, API endpoints work."""
        _, client, _, _ = app_and_client
        client.post("/admin/login",
                    data={"type": "password", "password": "test-admin-pw", "next": "/admin/dashboard"})
        resp = client.get("/admin/api/summary")
        assert resp.status_code == 200

    def test_logout_then_access_denied(self, app_and_client, admin_token):
        """After logout, dashboard redirects to login."""
        _, client, _, _ = app_and_client
        raw, _, _, _ = admin_token
        # Login first
        client.post("/admin/login", data={"type": "key", "key": raw, "next": "/admin/dashboard"})
        # Verify access
        resp = client.get("/admin/dashboard")
        assert resp.status_code == 200
        # Logout
        client.get("/admin/logout")
        # Access should redirect to login
        resp = client.get("/admin/dashboard", follow_redirects=False)
        assert resp.status_code == 302
        assert "/admin/login" in resp.headers["location"]


# ---------------------------------------------------------------------------
# Tests: i18n (internationalization)
# ---------------------------------------------------------------------------

class TestI18n:
    def test_default_locale_is_zh_cn(self, app_and_client):
        """GET /admin/login default shows Chinese content."""
        _, client, _, _ = app_and_client
        resp = client.get("/admin/login")
        assert resp.status_code == 200
        # Should contain Chinese text by default
        assert "管理后台" in resp.text
        assert "登录" in resp.text or "管理" in resp.text

    def test_lang_query_sets_cookie_and_redirects(self, app_and_client):
        """GET /admin/login?lang=en sets cookie and redirects, then shows English."""
        _, client, _, _ = app_and_client
        # Request with ?lang=en should redirect and set cookie
        resp = client.get("/admin/login?lang=en", follow_redirects=False)
        assert resp.status_code == 302
        # Should have set locale cookie
        set_cookie = resp.headers.get("set-cookie", "")
        assert "ss_admin_locale" in set_cookie
        assert "en" in set_cookie
        # Redirected URL should not contain lang param
        location = resp.headers["location"]
        assert "lang=" not in location

        # Follow the redirect — page should be English now
        resp = client.get(location)
        assert resp.status_code == 200
        assert "Smart Search Admin" in resp.text
        assert "Sign in" in resp.text

    def test_accept_language_en(self, app_and_client):
        """Accept-Language: en results in English page (no cookie/lang param)."""
        _, client, _, _ = app_and_client
        resp = client.get("/admin/login", headers={"Accept-Language": "en-US,en;q=0.9"})
        assert resp.status_code == 200
        assert "Smart Search Admin" in resp.text
        assert "Sign in" in resp.text

    def test_locale_cookie_persists(self, app_and_client):
        """After setting locale via ?lang=en, subsequent requests stay English."""
        _, client, _, _ = app_and_client
        # Set locale via ?lang=en
        client.get("/admin/login?lang=en", follow_redirects=False)
        # Subsequent request without lang param should use cookie
        resp = client.get("/admin/login")
        assert resp.status_code == 200
        assert "Smart Search Admin" in resp.text

    def test_dashboard_default_zh_cn(self, app_and_client, admin_token):
        """Dashboard page defaults to Chinese."""
        _, client, _, _ = app_and_client
        raw, _, _, _ = admin_token
        resp = client.get("/admin/dashboard", headers={"Authorization": f"Bearer {raw}"})
        assert resp.status_code == 200
        assert "仪表盘" in resp.text

    def test_tokens_page_default_zh_cn(self, app_and_client, admin_token):
        """Tokens page defaults to Chinese."""
        _, client, _, _ = app_and_client
        raw, _, _, _ = admin_token
        resp = client.get("/admin/tokens", headers={"Authorization": f"Bearer {raw}"})
        assert resp.status_code == 200
        assert "令牌" in resp.text

    def test_json_api_unaffected_by_locale(self, app_and_client, admin_token):
        """JSON API returns same data regardless of locale."""
        _, client, _, _ = app_and_client
        raw, _, _, _ = admin_token

        # Set locale cookie to en
        client.get("/admin/dashboard?lang=en", headers={"Authorization": f"Bearer {raw}"}, follow_redirects=False)
        resp_en = client.get("/admin/api/summary", headers={"Authorization": f"Bearer {raw}"})
        assert resp_en.status_code == 200
        data_en = resp_en.json()

        # Set locale cookie to zh-CN
        client.get("/admin/dashboard?lang=zh-CN", headers={"Authorization": f"Bearer {raw}"}, follow_redirects=False)
        resp_zh = client.get("/admin/api/summary", headers={"Authorization": f"Bearer {raw}"})
        assert resp_zh.status_code == 200
        data_zh = resp_zh.json()

        # JSON structure should be identical (same keys)
        assert set(data_en.keys()) == set(data_zh.keys())

    def test_lang_switch_link_present(self, app_and_client):
        """Login page has a language switch link."""
        _, client, _, _ = app_and_client
        resp = client.get("/admin/login")
        assert resp.status_code == 200
        # Default zh-CN, should show "English" link
        assert "English" in resp.text
        # Link should point to ?lang=en
        assert "lang=en" in resp.text

    def test_lang_switch_link_en_shows_zh(self, app_and_client):
        """English page shows 中文 switch link."""
        _, client, _, _ = app_and_client
        client.get("/admin/login?lang=en", follow_redirects=False)
        resp = client.get("/admin/login")
        assert "中文" in resp.text


# ---------------------------------------------------------------------------
# Tests: Usage Stats / Analytics API
# ---------------------------------------------------------------------------

class TestUsageStatsAPI:
    def test_usage_stats_default_period(self, app_and_client, admin_token):
        _, client, _, _ = app_and_client
        raw, _, _, _ = admin_token

        resp = client.get("/admin/api/usage/stats", headers={"Authorization": f"Bearer {raw}"})
        assert resp.status_code == 200
        data = resp.json()
        assert "total" in data
        assert "errors" in data
        assert "success_rate" in data
        assert "avg_elapsed_ms" in data
        assert "by_tool" in data
        assert "by_provider" in data
        assert "top_errors" in data
        assert "trend" in data

    def test_usage_stats_period_7d(self, app_and_client, admin_token):
        _, client, _, _ = app_and_client
        raw, _, _, _ = admin_token

        resp = client.get("/admin/api/usage/stats?period=7d", headers={"Authorization": f"Bearer {raw}"})
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data["total"], int)
        assert isinstance(data["success_rate"], (int, float))
        assert isinstance(data["trend"], list)

    def test_usage_stats_invalid_period_defaults_24h(self, app_and_client, admin_token):
        _, client, _, _ = app_and_client
        raw, _, _, _ = admin_token

        resp = client.get("/admin/api/usage/stats?period=1y", headers={"Authorization": f"Bearer {raw}"})
        assert resp.status_code == 200
        # Should still work (defaults to 24h)
        assert "total" in resp.json()

    def test_usage_stats_with_data(self, app_and_client, admin_token):
        """Create tool invocations and verify they appear in stats."""
        _, client, engine, session_factory = app_and_client
        raw, _, tenant, _ = admin_token

        from smart_search.storage.repositories import record_tool_invocation

        sess = session_factory()
        record_tool_invocation(
            sess, tenant_id=tenant.id, request_id="r1", tool="search",
            provider="xai-responses", is_ok=True, elapsed_ms=150,
        )
        record_tool_invocation(
            sess, tenant_id=tenant.id, request_id="r2", tool="search",
            provider="exa", is_ok=True, elapsed_ms=200,
        )
        record_tool_invocation(
            sess, tenant_id=tenant.id, request_id="r3", tool="fetch",
            provider="context7", is_ok=False, elapsed_ms=50,
            error_type="timeout",
        )
        sess.commit()
        sess.close()

        resp = client.get("/admin/api/usage/stats?period=24h", headers={"Authorization": f"Bearer {raw}"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 3
        assert data["errors"] == 1
        assert data["success_rate"] == round(2 / 3, 4)
        assert data["avg_elapsed_ms"] == 133  # (150+200+50)/3

        # by_tool
        assert "search" in data["by_tool"]
        assert data["by_tool"]["search"]["total"] == 2
        assert "fetch" in data["by_tool"]
        assert data["by_tool"]["fetch"]["total"] == 1

        # by_provider
        assert "xai-responses" in data["by_provider"]
        assert "exa" in data["by_provider"]
        assert "context7" in data["by_provider"]

        # top_errors
        assert len(data["top_errors"]) >= 1
        assert data["top_errors"][0]["error_type"] == "timeout"

        # trend
        assert len(data["trend"]) >= 1


# ---------------------------------------------------------------------------
# Tests: Task Analytics API
# ---------------------------------------------------------------------------

class TestTaskAnalyticsAPI:
    def test_task_analytics_empty(self, app_and_client, admin_token):
        _, client, _, _ = app_and_client
        raw, _, _, _ = admin_token

        resp = client.get("/admin/api/tasks/analytics", headers={"Authorization": f"Bearer {raw}"})
        assert resp.status_code == 200
        data = resp.json()
        assert "status_counts" in data
        assert "recent_tasks" in data

    def test_task_analytics_with_data(self, app_and_client, admin_token):
        _, client, engine, session_factory = app_and_client
        raw, _, tenant, _ = admin_token

        from smart_search.storage.repositories import create_task_run, create_task_node, update_node_status

        sess = session_factory()
        tr = create_task_run(sess, tenant_id=tenant.id, task_type="deep_research", topic="test topic")
        n1 = create_task_node(sess, task_run_id=tr.id, node_type="search", name="search-1", status="completed")
        n2 = create_task_node(sess, task_run_id=tr.id, node_type="analyze", name="analyze-1", status="pending")
        sess.commit()
        sess.close()

        resp = client.get("/admin/api/tasks/analytics", headers={"Authorization": f"Bearer {raw}"})
        assert resp.status_code == 200
        data = resp.json()
        assert "queued" in data["status_counts"] or "running" in data["status_counts"] or "completed" in data["status_counts"]
        assert len(data["recent_tasks"]) >= 1
        task = data["recent_tasks"][0]
        assert "progress" in task
        assert task["progress"]["total_nodes"] == 2
        assert task["progress"]["completed_nodes"] == 1
        assert task["progress"]["pct"] == 50.0


# ---------------------------------------------------------------------------
# Tests: Provider Groups API
# ---------------------------------------------------------------------------

class TestProviderGroupsAPI:
    def test_provider_groups_empty(self, app_and_client, admin_token):
        _, client, _, _ = app_and_client
        raw, _, _, _ = admin_token

        resp = client.get("/admin/api/providers/groups", headers={"Authorization": f"Bearer {raw}"})
        assert resp.status_code == 200
        assert resp.json() == []

    def test_provider_groups_with_data(self, app_and_client, admin_token):
        _, client, engine, session_factory = app_and_client
        raw, _, tenant, _ = admin_token

        from smart_search.storage.repositories import (
            create_provider_credential, create_provider_config,
        )

        sess = session_factory()
        create_provider_credential(sess, tenant_id=tenant.id, provider="xai-responses", masked_value="sk-***")
        create_provider_config(sess, tenant_id=tenant.id, provider="xai-responses", capability="main_search", priority=10)
        create_provider_config(sess, tenant_id=tenant.id, provider="xai-responses", capability="fallback", is_enabled=False)
        create_provider_credential(sess, tenant_id=tenant.id, provider="exa", masked_value="ex-***")
        sess.commit()
        sess.close()

        resp = client.get("/admin/api/providers/groups", headers={"Authorization": f"Bearer {raw}"})
        assert resp.status_code == 200
        groups = resp.json()
        assert len(groups) == 2

        # Find xai-responses group
        xai_group = next(g for g in groups if g["provider"] == "xai-responses")
        assert xai_group["credential_count"] == 1
        assert xai_group["config_count"] == 2
        assert xai_group["has_active_credential"] is True
        assert xai_group["has_enabled_config"] is True
        assert len(xai_group["credentials"]) == 1
        assert len(xai_group["configs"]) == 2

        # Find exa group
        exa_group = next(g for g in groups if g["provider"] == "exa")
        assert exa_group["credential_count"] == 1
        assert exa_group["config_count"] == 0


# ---------------------------------------------------------------------------
# Tests: Provider Config Update / Toggle API
# ---------------------------------------------------------------------------

class TestProviderConfigUpdateAPI:
    def test_update_config(self, app_and_client, admin_token):
        _, client, _, _ = app_and_client
        raw, _, _, _ = admin_token

        # Create a config first
        resp = client.post(
            "/admin/api/providers/configs",
            json={"provider": "test-provider", "capability": "search", "priority": 5, "settings": {"k": "v"}},
            headers={"Authorization": f"Bearer {raw}"},
        )
        assert resp.status_code == 201
        config_id = resp.json()["id"]

        # Update it
        resp = client.put(
            f"/admin/api/providers/configs/{config_id}",
            json={"priority": 20, "settings": {"k": "updated"}, "is_enabled": False},
            headers={"Authorization": f"Bearer {raw}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["priority"] == 20
        assert data["settings"] == {"k": "updated"}
        assert data["is_enabled"] is False

    def test_update_config_not_found(self, app_and_client, admin_token):
        _, client, _, _ = app_and_client
        raw, _, _, _ = admin_token

        resp = client.put(
            "/admin/api/providers/configs/nonexistent-id",
            json={"priority": 10},
            headers={"Authorization": f"Bearer {raw}"},
        )
        assert resp.status_code == 404

    def test_toggle_config(self, app_and_client, admin_token):
        _, client, _, _ = app_and_client
        raw, _, _, _ = admin_token

        # Create an enabled config
        resp = client.post(
            "/admin/api/providers/configs",
            json={"provider": "toggle-provider", "capability": "search", "is_enabled": True},
            headers={"Authorization": f"Bearer {raw}"},
        )
        assert resp.status_code == 201
        config_id = resp.json()["id"]
        assert resp.json()["is_enabled"] is True

        # Toggle to disabled
        resp = client.post(
            f"/admin/api/providers/configs/{config_id}/toggle",
            headers={"Authorization": f"Bearer {raw}"},
        )
        assert resp.status_code == 200
        assert resp.json()["is_enabled"] is False

        # Toggle back to enabled
        resp = client.post(
            f"/admin/api/providers/configs/{config_id}/toggle",
            headers={"Authorization": f"Bearer {raw}"},
        )
        assert resp.status_code == 200
        assert resp.json()["is_enabled"] is True

    def test_toggle_config_not_found(self, app_and_client, admin_token):
        _, client, _, _ = app_and_client
        raw, _, _, _ = admin_token

        resp = client.post(
            "/admin/api/providers/configs/nonexistent-id/toggle",
            headers={"Authorization": f"Bearer {raw}"},
        )
        assert resp.status_code == 404
