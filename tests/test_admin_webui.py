"""Admin WebUI and API tests.

Uses TestClient + SQLite tmp. No network.
Covers: admin token access, non-admin 403, token create (raw only in response),
provider credential create+reveal+audit, disable token/provider, summary/usage/audit pages.
"""

from __future__ import annotations

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

    from httpx import ASGITransport, AsyncClient
    # Use sync TestClient for simplicity
    from starlette.testclient import TestClient
    client = TestClient(app)

    yield app, client, engine, session_factory

    Base.metadata.drop_all(bind=engine)
    engine.dispose()


@pytest.fixture()
def admin_token(app_and_client):
    """Create an admin token and return (raw_token_string, api_token_obj)."""
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
# Tests
# ---------------------------------------------------------------------------

class TestAdminAuth:
    def test_admin_can_access_dashboard(self, app_and_client, admin_token):
        _, client, _, _ = app_and_client
        raw, _, _, _ = admin_token
        resp = client.get("/admin/dashboard", headers={"Authorization": f"Bearer {raw}"})
        assert resp.status_code == 200
        assert "Dashboard" in resp.text

    def test_non_admin_gets_403(self, app_and_client, non_admin_token):
        _, client, _, _ = app_and_client
        resp = client.get("/admin/dashboard", headers={"Authorization": f"Bearer {non_admin_token}"})
        assert resp.status_code == 403

    def test_no_auth_gets_401(self, app_and_client):
        _, client, _, _ = app_and_client
        resp = client.get("/admin/dashboard")
        assert resp.status_code == 401

    def test_cookie_auth(self, app_and_client, admin_token):
        _, client, _, _ = app_and_client
        raw, _, _, _ = admin_token
        # Use ?token= query param which sets cookie
        resp = client.get(f"/admin/dashboard?token={raw}", follow_redirects=True)
        assert resp.status_code == 200
        # Check cookie was set
        cookies = resp.cookies
        assert "ss_admin_session" in cookies or resp.headers.get("set-cookie", "")


class TestAdminTokenAPI:
    def test_create_token_raw_shown_once(self, app_and_client, admin_token):
        _, client, _, _ = app_and_client
        raw, _, tenant, user = admin_token

        # Create a new token via admin API
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

        # The raw token should NOT be stored in DB as plaintext
        # (it's hashed — we verify by checking token_prefix is stored but not raw)
        assert "token_prefix" in data
        assert data["token_prefix"] != data["raw_token"]

    def test_disable_token(self, app_and_client, admin_token):
        _, client, _, _ = app_and_client
        raw, _, _, _ = admin_token

        # Create a token
        resp = client.post(
            "/admin/api/tokens",
            json={"name": "to-disable", "scopes": {"permissions": ["search:read"]}},
            headers={"Authorization": f"Bearer {raw}"},
        )
        token_id = resp.json()["id"]

        # Disable it
        resp = client.post(
            f"/admin/api/tokens/{token_id}/disable",
            headers={"Authorization": f"Bearer {raw}"},
        )
        assert resp.status_code == 200
        assert resp.json()["is_active"] is False

        # Verify in list
        resp = client.get("/admin/api/tokens", headers={"Authorization": f"Bearer {raw}"})
        tokens = resp.json()
        disabled = [t for t in tokens if t["id"] == token_id]
        assert len(disabled) == 1
        assert disabled[0]["is_active"] is False


class TestAdminProviderAPI:
    def test_create_credential_and_reveal(self, app_and_client, admin_token):
        _, client, _, _ = app_and_client
        raw, _, _, _ = admin_token

        # Create a credential
        resp = client.post(
            "/admin/api/providers/credentials",
            json={"provider": "xai-responses", "api_key": "sk-xai-test-secret-key"},
            headers={"Authorization": f"Bearer {raw}"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["provider"] == "xai-responses"
        assert data["masked_value"]  # should be masked
        assert "sk-xai" not in data["masked_value"]  # actually masked
        cred_id = data["id"]

        # Reveal it
        resp = client.post(
            f"/admin/api/providers/credentials/{cred_id}/reveal",
            headers={"Authorization": f"Bearer {raw}"},
        )
        assert resp.status_code == 200
        assert resp.headers.get("cache-control") == "no-store"
        reveal = resp.json()
        assert reveal["api_key"] == "sk-xai-test-secret-key"

        # Check audit event was recorded
        resp = client.get("/admin/api/audit", headers={"Authorization": f"Bearer {raw}"})
        events = resp.json()
        reveal_events = [e for e in events if e["action"] == "provider_key.reveal"]
        assert len(reveal_events) >= 1

    def test_disable_credential(self, app_and_client, admin_token):
        _, client, _, _ = app_and_client
        raw, _, _, _ = admin_token

        # Create a credential
        resp = client.post(
            "/admin/api/providers/credentials",
            json={"provider": "exa", "api_key": "sk-exa-key"},
            headers={"Authorization": f"Bearer {raw}"},
        )
        cred_id = resp.json()["id"]

        # Disable it
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

        # List configs
        resp = client.get("/admin/api/providers/configs", headers={"Authorization": f"Bearer {raw}"})
        configs = resp.json()
        assert any(c["provider"] == "xai-responses" for c in configs)


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
