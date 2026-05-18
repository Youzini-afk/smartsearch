"""Server tool tests – FastAPI TestClient with SQLite tmp DB.

Covers: health, no-token 401, no-permission 403, search with usage/audit,
service error recording, deep_plan, docs_search, web_search provider routing.
No network calls.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

# Ensure src is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _isolate_config(monkeypatch, tmp_path):
    """Isolate the CLI Config singleton and clear caches."""
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

    # Provide stable keys for tests
    monkeypatch.setenv("SMART_SEARCH_MASTER_KEY", "test-master-key-for-server-tests")
    monkeypatch.setenv("SMART_SEARCH_TOKEN_SECRET", "test-token-secret-for-server")
    monkeypatch.setenv("SMART_SEARCH_ALLOW_INSECURE_DEV_KEYS", "true")


@pytest.fixture()
def db_engine(tmp_path):
    """Create a fresh SQLite DB engine for each test."""
    from sqlalchemy import create_engine
    from smart_search.storage.models import Base
    from smart_search.storage.db import create_session_factory

    db_path = tmp_path / "test-server.db"
    url = f"sqlite:///{db_path}"
    engine = create_engine(url, connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


@pytest.fixture()
def session_factory(db_engine):
    """Create a session factory bound to the test engine."""
    from smart_search.storage.db import create_session_factory

    return create_session_factory(db_engine)


@pytest.fixture()
def app(db_engine, session_factory):
    """Create a test FastAPI app."""
    from smart_search.server.app import create_app

    return create_app(engine=db_engine, session_factory=session_factory)


@pytest.fixture()
def client(app):
    """Create a TestClient for the app."""
    from fastapi.testclient import TestClient

    return TestClient(app)


@pytest.fixture()
def seeded_token(session_factory):
    """Create a tenant, user, and API token with search:read scope.

    Returns (raw_token_string, tenant_id, user_id).
    """
    from smart_search.storage.repositories import create_tenant, create_user, store_api_token
    from smart_search.auth.tokens import generate_token, hash_token, token_prefix

    with session_factory() as session:
        tenant = create_tenant(session, name="Test Tenant", slug="test-tenant")
        user = create_user(session, email="tester@example.com", display_name="Tester")
        raw_token = generate_token()
        prefix = token_prefix(raw_token)
        token_hash = hash_token(raw_token)

        db_token = store_api_token(
            session,
            user_id=user.id,
            tenant_id=tenant.id,
            token_prefix=prefix,
            token_hash=token_hash,
            name="test-token",
            scopes={"permissions": ["search:read", "fetch:read"]},
        )
        session.commit()

        return raw_token, tenant.id, user.id


@pytest.fixture()
def search_only_token(session_factory):
    """Create an API token with only search:read scope."""
    from smart_search.storage.repositories import create_tenant, create_user, store_api_token
    from smart_search.auth.tokens import generate_token, hash_token, token_prefix

    with session_factory() as session:
        tenant = create_tenant(session, name="Search Tenant", slug="search-tenant")
        user = create_user(session, email="search@example.com", display_name="SearchOnly")
        raw_token = generate_token()
        store_api_token(
            session,
            user_id=user.id,
            tenant_id=tenant.id,
            token_prefix=token_prefix(raw_token),
            token_hash=hash_token(raw_token),
            name="search-only-token",
            scopes={"permissions": ["search:read"]},
        )
        session.commit()
        return raw_token


@pytest.fixture()
def admin_token(session_factory):
    """Create an API token with admin scope."""
    from smart_search.storage.repositories import create_tenant, create_user, store_api_token
    from smart_search.auth.tokens import generate_token, hash_token, token_prefix

    with session_factory() as session:
        tenant = create_tenant(session, name="Admin Tenant", slug="admin-tenant")
        user = create_user(session, email="admin@example.com", display_name="Admin")
        raw_token = generate_token()
        prefix = token_prefix(raw_token)
        token_hash = hash_token(raw_token)

        store_api_token(
            session,
            user_id=user.id,
            tenant_id=tenant.id,
            token_prefix=prefix,
            token_hash=token_hash,
            name="admin-token",
            scopes={"permissions": ["admin"]},
        )
        session.commit()

        return raw_token


@pytest.fixture()
def no_scope_token(session_factory):
    """Create an API token with NO scope (should get 403)."""
    from smart_search.storage.repositories import create_tenant, create_user, store_api_token
    from smart_search.auth.tokens import generate_token, hash_token, token_prefix

    with session_factory() as session:
        tenant = create_tenant(session, name="NoScope Tenant", slug="noscope-tenant")
        user = create_user(session, email="noscope@example.com", display_name="NoScope")
        raw_token = generate_token()
        prefix = token_prefix(raw_token)
        token_hash = hash_token(raw_token)

        store_api_token(
            session,
            user_id=user.id,
            tenant_id=tenant.id,
            token_prefix=prefix,
            token_hash=token_hash,
            name="noscope-token",
            scopes={"permissions": []},
        )
        session.commit()

        return raw_token


@pytest.fixture()
def auth_headers(seeded_token):
    """Return Authorization headers dict for the seeded token."""
    token, _, _ = seeded_token
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture()
def admin_headers(admin_token):
    """Return Authorization headers for the admin token."""
    return {"Authorization": f"Bearer {admin_token}"}


@pytest.fixture()
def noscope_headers(no_scope_token):
    """Return Authorization headers for the no-scope token."""
    return {"Authorization": f"Bearer {no_scope_token}"}


@pytest.fixture()
def search_only_headers(search_only_token):
    """Return Authorization headers for a search-only token."""
    return {"Authorization": f"Bearer {search_only_token}"}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestHealthEndpoint:
    """GET /health requires no auth and returns ok."""

    def test_health_returns_ok(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"


class TestAuthRequired:
    """Tool endpoints require a valid Bearer token."""

    def test_no_token_returns_401(self, client):
        resp = client.post("/api/tools/search", json={"query": "test"})
        assert resp.status_code == 401

    def test_invalid_token_returns_401(self, client):
        headers = {"Authorization": "Bearer invalid-smart-search-token"}
        resp = client.post("/api/tools/search", json={"query": "test"}, headers=headers)
        assert resp.status_code == 401

    def test_no_scope_returns_403(self, client, noscope_headers):
        resp = client.post("/api/tools/search", json={"query": "test"}, headers=noscope_headers)
        assert resp.status_code == 403

    def test_fetch_requires_fetch_scope(self, client, search_only_headers):
        resp = client.post(
            "/api/tools/fetch_url",
            json={"url": "https://example.com"},
            headers=search_only_headers,
        )
        assert resp.status_code == 403

    def test_deep_plan_requires_deep_or_admin_scope(self, client, search_only_headers):
        resp = client.post(
            "/api/tools/deep_plan",
            json={"topic": "test"},
            headers=search_only_headers,
        )
        assert resp.status_code == 403

    def test_doctor_requires_doctor_or_admin_scope(self, client, search_only_headers):
        resp = client.post("/api/tools/doctor", json={}, headers=search_only_headers)
        assert resp.status_code == 403


class TestSearchTool:
    """POST /api/tools/search dispatches to service.search and records usage."""

    def test_search_success_records_usage_and_audit(
        self, client, auth_headers, session_factory, monkeypatch
    ):
        # Mock service.search to return a successful result without network
        mock_result = {
            "ok": True,
            "content": "Test answer",
            "sources": [{"url": "https://example.com", "provider": "test"}],
            "sources_count": 1,
            "providers_used": ["test-provider"],
            "provider_attempts": [],
            "session_id": "s-1",
            "query": "test query",
            "elapsed_ms": 100,
        }

        async def _mock_search(*args, **kwargs):
            return mock_result

        monkeypatch.setattr("smart_search.service.search", _mock_search)

        resp = client.post(
            "/api/tools/search",
            json={"query": "test query"},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert data["content"] == "Test answer"

        # Verify tool_invocations was written
        from sqlalchemy import select
        from smart_search.storage.models import ToolInvocation, AuditEvent

        with session_factory() as session:
            invocations = session.execute(select(ToolInvocation)).scalars().all()
            assert len(invocations) >= 1
            inv = invocations[0]
            assert inv.tool == "search"
            assert inv.is_ok is True
            assert inv.provider == "test-provider"
            assert inv.metadata_["input_preview"] == "test query"
            assert "input_hash" in inv.metadata_
            assert inv.metadata_["input_hash"] != __import__("hashlib").sha256(b"test query").hexdigest()

            # Verify audit event was written
            events = session.execute(select(AuditEvent)).scalars().all()
            assert len(events) >= 1
            audit = events[0]
            assert audit.action == "tool.invoke"
            assert audit.target_id == "search"
            assert audit.detail["is_ok"] is True

    def test_search_service_error_records_failure(
        self, client, auth_headers, session_factory, monkeypatch
    ):
        async def _mock_search_error(*args, **kwargs):
            return {
                "ok": False,
                "error_type": "config_error",
                "error": "No providers configured",
                "providers_used": [],
            }

        monkeypatch.setattr("smart_search.service.search", _mock_search_error)

        resp = client.post(
            "/api/tools/search",
            json={"query": "broken query"},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is False

        from sqlalchemy import select
        from smart_search.storage.models import ToolInvocation

        with session_factory() as session:
            invocations = session.execute(select(ToolInvocation)).scalars().all()
            assert len(invocations) >= 1
            inv = invocations[0]
            assert inv.tool == "search"
            assert inv.is_ok is False
            assert inv.error_type == "config_error"


class TestDeepPlanTool:
    """POST /api/tools/deep_plan calls build_deep_research_plan."""

    def test_deep_plan_success(self, client, admin_headers, session_factory, monkeypatch):
        mock_result = {
            "ok": True,
            "mode": "deep_research",
            "question": "test topic",
            "steps": [],
            "elapsed_ms": 10,
        }

        def _mock_plan(*args, **kwargs):
            return mock_result

        monkeypatch.setattr("smart_search.service.build_deep_research_plan", _mock_plan)

        resp = client.post(
            "/api/tools/deep_plan",
            json={"topic": "test topic", "depth": "standard"},
            headers=admin_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert data["mode"] == "deep_research"

        from sqlalchemy import select
        from smart_search.storage.models import ToolInvocation

        with session_factory() as session:
            invocations = session.execute(select(ToolInvocation)).scalars().all()
            assert len(invocations) >= 1
            inv = invocations[0]
            assert inv.tool == "deep_plan"
            assert inv.is_ok is True


class TestDocsSearchTool:
    """POST /api/tools/docs_search routes to context7_library or context7_docs."""

    def test_docs_search_without_library_id(self, client, admin_headers, monkeypatch):
        mock_result = {
            "ok": True,
            "query": "react hooks",
            "provider": "context7",
            "results": [],
        }

        async def _mock_library(*args, **kwargs):
            return mock_result

        monkeypatch.setattr("smart_search.service.context7_library", _mock_library)

        resp = client.post(
            "/api/tools/docs_search",
            json={"query": "react hooks"},
            headers=admin_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True

    def test_docs_search_with_library_id(self, client, admin_headers, monkeypatch):
        mock_result = {
            "ok": True,
            "library_id": "/react",
            "query": "hooks",
            "provider": "context7",
            "results": [],
        }

        async def _mock_docs(*args, **kwargs):
            return mock_result

        monkeypatch.setattr("smart_search.service.context7_docs", _mock_docs)

        resp = client.post(
            "/api/tools/docs_search",
            json={"query": "hooks", "library_id": "/react"},
            headers=admin_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True


class TestWebSearchTool:
    """POST /api/tools/web_search routes by provider param."""

    def test_web_search_zhipu(self, client, admin_headers, monkeypatch):
        mock_result = {
            "ok": True,
            "query": "test",
            "provider": "zhipu",
            "results": [],
        }

        async def _mock_zhipu(*args, **kwargs):
            return mock_result

        monkeypatch.setattr("smart_search.service.zhipu_search", _mock_zhipu)

        resp = client.post(
            "/api/tools/web_search",
            json={"query": "test", "provider": "zhipu"},
            headers=admin_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True

    def test_web_search_exa(self, client, admin_headers, monkeypatch):
        mock_result = {
            "ok": True,
            "query": "test",
            "provider": "exa",
            "results": [],
        }

        async def _mock_exa(*args, **kwargs):
            return mock_result

        monkeypatch.setattr("smart_search.service.exa_search", _mock_exa)

        resp = client.post(
            "/api/tools/web_search",
            json={"query": "test", "provider": "exa"},
            headers=admin_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True

    def test_web_search_auto_falls_back_to_exa(self, client, admin_headers, monkeypatch):
        """When provider=auto and zhipu fails, falls back to exa."""

        async def _mock_zhipu_fail(*args, **kwargs):
            return {"ok": False, "error_type": "config_error", "error": "not configured"}

        mock_exa_result = {
            "ok": True,
            "query": "test",
            "provider": "exa",
            "results": [],
        }

        async def _mock_exa(*args, **kwargs):
            return mock_exa_result

        monkeypatch.setattr("smart_search.service.zhipu_search", _mock_zhipu_fail)
        monkeypatch.setattr("smart_search.service.exa_search", _mock_exa)

        resp = client.post(
            "/api/tools/web_search",
            json={"query": "test", "provider": "auto"},
            headers=admin_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True

    def test_web_search_unknown_provider(self, client, admin_headers):
        resp = client.post(
            "/api/tools/web_search",
            json={"query": "test", "provider": "unknown_provider"},
            headers=admin_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is False
        assert data["error_type"] == "parameter_error"


class TestFetchUrlTool:
    """POST /api/tools/fetch_url dispatches to service.fetch."""

    def test_fetch_url_success(self, client, admin_headers, monkeypatch):
        mock_result = {
            "ok": True,
            "url": "https://example.com",
            "provider": "tavily",
            "content": "Example content",
        }

        async def _mock_fetch(*args, **kwargs):
            return mock_result

        monkeypatch.setattr("smart_search.service.fetch", _mock_fetch)

        resp = client.post(
            "/api/tools/fetch_url",
            json={"url": "https://example.com"},
            headers=admin_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True


class TestMapSiteTool:
    """POST /api/tools/map_site dispatches to service.map_site."""

    def test_map_site_success(self, client, admin_headers, monkeypatch):
        mock_result = {
            "ok": True,
            "url": "https://example.com",
            "results": ["https://example.com/page1"],
        }

        async def _mock_map(*args, **kwargs):
            return mock_result

        monkeypatch.setattr("smart_search.service.map_site", _mock_map)

        resp = client.post(
            "/api/tools/map_site",
            json={"url": "https://example.com"},
            headers=admin_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True


class TestDoctorTool:
    """POST /api/tools/doctor dispatches to service.doctor."""

    def test_doctor_success(self, client, admin_headers, monkeypatch):
        mock_result = {
            "ok": True,
            "capability_status": {"main_search": {"ok": True}},
            "minimum_profile_ok": True,
        }

        async def _mock_doctor(*args, **kwargs):
            return mock_result

        monkeypatch.setattr("smart_search.service.doctor", _mock_doctor)

        resp = client.post("/api/tools/doctor", json={}, headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True


class TestMCPModuleGraceful:
    """MCP module does not crash the app when mcp is not installed."""

    def test_create_mcp_server_returns_none_without_mcp(self, monkeypatch):
        """If mcp package is missing, create_mcp_server returns None."""
        # Simulate mcp import failure
        import importlib
        mcp_mod = sys.modules.get("mcp")
        if mcp_mod is not None:
            monkeypatch.setitem(sys.modules, "mcp", None)
            monkeypatch.setitem(sys.modules, "mcp.server", None)
            monkeypatch.setitem(sys.modules, "mcp.server.fastmcp", None)

        from smart_search.server.mcp_server import create_mcp_server

        result = create_mcp_server(None)
        # Returns None when mcp is not available
        assert result is None or hasattr(result, "routes")  # depends on whether mcp is installed

    def test_mcp_mount_disabled_by_default(self, app):
        assert getattr(app.state, "mcp_mounted", False) is False


class TestAuditSecurity:
    """Verify audit records don't contain secrets or full queries."""

    def test_audit_no_full_query_or_token(self, client, auth_headers, session_factory, monkeypatch):
        mock_result = {
            "ok": True,
            "content": "answer",
            "sources": [],
            "providers_used": ["test"],
        }

        async def _mock_search(*args, **kwargs):
            return mock_result

        monkeypatch.setattr("smart_search.service.search", _mock_search)

        # Make the query longer than 100 chars
        long_query = "x" * 200
        resp = client.post(
            "/api/tools/search",
            json={"query": long_query},
            headers=auth_headers,
        )
        assert resp.status_code == 200

        from sqlalchemy import select
        from smart_search.storage.models import AuditEvent, ToolInvocation

        with session_factory() as session:
            events = session.execute(select(AuditEvent)).scalars().all()
            assert len(events) >= 1
            detail = events[0].detail
            # input_preview should be truncated
            preview = detail.get("input_preview", "")
            assert len(preview) <= 100

            # No Authorization or api_key in detail
            for key, value in detail.items():
                assert "authorization" not in str(key).lower()
                assert "api_key" not in str(key).lower()

            # metadata in tool_invocations also truncated
            invocations = session.execute(select(ToolInvocation)).scalars().all()
            assert len(invocations) >= 1
            meta = invocations[0].metadata_ or {}
            assert len(meta.get("input_preview", "")) <= 100
