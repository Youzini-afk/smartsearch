"""Admin WebUI and API tests.

Uses TestClient + SQLite tmp. No network.
Covers: admin token access, non-admin 403, token create (raw only in response),
provider credential create+reveal+audit, disable token/provider, summary/usage/audit pages,
login page, password auth, redirect flows, logout.
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
        assert "Smart Search Admin" in resp.text
        assert "API Key" in resp.text
        assert "Password" in resp.text

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
        assert "Dashboard" in resp.text

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
        assert "Dashboard" in resp.text


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

    def test_usage_page(self, app_and_client, admin_token):
        _, client, _, _ = app_and_client
        raw, _, _, _ = admin_token

        resp = client.get("/admin/usage", headers={"Authorization": f"Bearer {raw}"})
        assert resp.status_code == 200
        assert "Invocations" in resp.text

    def test_audit_page(self, app_and_client, admin_token):
        _, client, _, _ = app_and_client
        raw, _, _, _ = admin_token

        resp = client.get("/admin/audit", headers={"Authorization": f"Bearer {raw}"})
        assert resp.status_code == 200
        assert "Audit" in resp.text

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
        assert "System" in resp.text


class TestAdminTokensPage:
    def test_tokens_page(self, app_and_client, admin_token):
        _, client, _, _ = app_and_client
        raw, _, _, _ = admin_token

        resp = client.get("/admin/tokens", headers={"Authorization": f"Bearer {raw}"})
        assert resp.status_code == 200
        assert "Tokens" in resp.text


class TestAdminProvidersPage:
    def test_providers_page(self, app_and_client, admin_token):
        _, client, _, _ = app_and_client
        raw, _, _, _ = admin_token

        resp = client.get("/admin/providers", headers={"Authorization": f"Bearer {raw}"})
        assert resp.status_code == 200
        assert "Providers" in resp.text


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
        assert "Dashboard" in resp.text

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
