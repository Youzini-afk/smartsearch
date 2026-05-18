"""Cloud foundation tests – DB init, models, tokens, crypto, config resolver, context.

All tests use in-memory / tmp SQLite. No network. No PostgreSQL.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from datetime import datetime, timezone, timedelta

import pytest

# Ensure src is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _isolate_config(monkeypatch, tmp_path):
    """Isolate the CLI Config singleton and clear master key caches."""
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

    # Provide a stable master key for tests
    monkeypatch.setenv("SMART_SEARCH_MASTER_KEY", "test-master-key-for-cloud-foundation-tests")
    monkeypatch.setenv("SMART_SEARCH_TOKEN_SECRET", "test-token-secret-for-cloud-foundation")


@pytest.fixture()
def db_engine(tmp_path):
    """Create a fresh SQLite DB engine + session for each test."""
    from sqlalchemy import create_engine
    from smart_search.storage.models import Base
    from smart_search.storage.db import create_session_factory

    db_path = tmp_path / "test-cloud.db"
    url = f"sqlite:///{db_path}"
    engine = create_engine(url, connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


@pytest.fixture()
def session(db_engine):
    """Provide a Session that auto-commits after the test."""
    from smart_search.storage.db import create_session_factory

    SessionFactory = create_session_factory(db_engine)
    sess = SessionFactory()
    yield sess
    sess.commit()
    sess.close()


# ---------------------------------------------------------------------------
# 1. DB Initialisation
# ---------------------------------------------------------------------------

class TestDBInit:
    def test_database_url_env_precedence(self, monkeypatch):
        from smart_search.storage import db

        monkeypatch.delenv("SMART_SEARCH_DATABASE_URL", raising=False)
        monkeypatch.delenv("POSTGRES_CONNECTION_STRING", raising=False)
        monkeypatch.delenv("DATABASE_URL", raising=False)
        assert db._database_url() == "sqlite:///smart-search-cloud.db"

        monkeypatch.setenv("DATABASE_URL", "sqlite:///generic.db")
        assert db._database_url() == "sqlite:///generic.db"

        monkeypatch.setenv("POSTGRES_CONNECTION_STRING", "postgresql+psycopg://zeabur")
        assert db._database_url() == "postgresql+psycopg://zeabur"

        monkeypatch.setenv("SMART_SEARCH_DATABASE_URL", "sqlite:///explicit.db")
        assert db._database_url() == "sqlite:///explicit.db"

    def test_init_db_creates_tables(self, tmp_path):
        from smart_search.storage.db import init_db, create_engine_from_url
        from smart_search.storage.models import Base

        url = f"sqlite:///{tmp_path / 'init-test.db'}"
        engine = create_engine_from_url(url)
        init_db(engine)

        # Verify tables exist by querying
        from sqlalchemy import inspect
        inspector = inspect(engine)
        table_names = inspector.get_table_names()
        assert "tenants" in table_names
        assert "users" in table_names
        assert "api_tokens" in table_names
        assert "provider_credentials" in table_names
        assert "provider_configs" in table_names
        assert "tool_invocations" in table_names
        assert "provider_usage" in table_names
        assert "audit_events" in table_names
        assert "memberships" in table_names
        engine.dispose()

    def test_init_db_idempotent(self, db_engine):
        from smart_search.storage.db import init_db
        # Calling twice should not raise
        init_db(db_engine)
        init_db(db_engine)

    def test_drop_db_for_tests(self, tmp_path):
        from smart_search.storage.db import init_db, drop_db_for_tests, create_engine_from_url
        from sqlalchemy import inspect

        url = f"sqlite:///{tmp_path / 'drop-test.db'}"
        engine = create_engine_from_url(url)
        init_db(engine)
        drop_db_for_tests(engine)

        inspector = inspect(engine)
        assert inspector.get_table_names() == []
        engine.dispose()


# ---------------------------------------------------------------------------
# 2. Tenant / User / Token CRUD
# ---------------------------------------------------------------------------

class TestTenantUserToken:
    def test_create_tenant(self, session):
        from smart_search.storage.repositories import create_tenant

        tenant = create_tenant(session, name="Acme Corp", slug="acme")
        assert tenant.id
        assert tenant.name == "Acme Corp"
        assert tenant.slug == "acme"
        assert tenant.is_active is True

    def test_get_tenant_by_slug(self, session):
        from smart_search.storage.repositories import create_tenant, get_tenant_by_slug

        create_tenant(session, name="Acme", slug="acme")
        found = get_tenant_by_slug(session, "acme")
        assert found is not None
        assert found.name == "Acme"

        not_found = get_tenant_by_slug(session, "nonexistent")
        assert not_found is None

    def test_create_user(self, session):
        from smart_search.storage.repositories import create_user

        user = create_user(session, email="alice@example.com", display_name="Alice")
        assert user.id
        assert user.email == "alice@example.com"

    def test_add_membership(self, session):
        from smart_search.storage.repositories import create_tenant, create_user, add_membership

        tenant = create_tenant(session, name="T", slug="t1")
        user = create_user(session, email="bob@example.com")
        m = add_membership(session, tenant_id=tenant.id, user_id=user.id, role="admin")
        assert m.role == "admin"
        assert m.tenant_id == tenant.id

    def test_create_and_verify_token(self, session):
        from smart_search.storage.repositories import create_tenant, create_user, store_api_token
        from smart_search.storage.models import Tenant, User
        from smart_search.auth.tokens import generate_token, hash_token, token_prefix, verify_token

        tenant = create_tenant(session, name="T", slug="t1")
        user = create_user(session, email="carol@example.com")
        raw_token = generate_token()
        assert raw_token.startswith("sk_live_")

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
        assert db_token.id

        # Verify the token
        found = verify_token(session, raw_token)
        assert found is not None
        assert found.user_id == user.id
        assert found.name == "test-token"

        # Wrong token should return None
        bad = verify_token(session, "not-a-smart-search-token")
        assert bad is None

    def test_expired_token_rejected(self, session):
        from smart_search.storage.repositories import create_tenant, create_user, store_api_token
        from smart_search.auth.tokens import generate_token, hash_token, token_prefix, verify_token

        tenant = create_tenant(session, name="T", slug="t2")
        user = create_user(session, email="dave@example.com")
        raw_token = generate_token()
        prefix = token_prefix(raw_token)
        token_hash = hash_token(raw_token)

        store_api_token(
            session,
            user_id=user.id,
            tenant_id=tenant.id,
            token_prefix=prefix,
            token_hash=token_hash,
            expires_at=datetime.now(timezone.utc) - timedelta(hours=1),
        )

        assert verify_token(session, raw_token) is None


# ---------------------------------------------------------------------------
# 3. Crypto – encrypt / decrypt / mask / fingerprint
# ---------------------------------------------------------------------------

class TestCrypto:
    def test_encrypt_decrypt_roundtrip(self):
        from smart_search.security.crypto import encrypt_secret, decrypt_secret

        plaintext = "sk-abc123secret"
        token = encrypt_secret(plaintext)
        assert token != plaintext
        recovered = decrypt_secret(token)
        assert recovered == plaintext

    def test_encrypt_with_explicit_key(self):
        from smart_search.security.crypto import encrypt_secret, decrypt_secret

        key = "my-very-secret-key"
        token = encrypt_secret("hello", key=key)
        recovered = decrypt_secret(token, key=key)
        assert recovered == "hello"

    def test_wrong_key_fails(self):
        from smart_search.security.crypto import encrypt_secret, decrypt_secret
        from cryptography.fernet import InvalidToken

        token = encrypt_secret("secret", key="key-a")
        with pytest.raises(InvalidToken):
            decrypt_secret(token, key="key-b")

    def test_mask_secret(self):
        from smart_search.security.crypto import mask_secret

        assert mask_secret("") == "***"
        assert mask_secret("ab") == "***"
        assert mask_secret("sk_live_abc123xyz789") == "sk_l…z789"

    def test_fingerprint_stable(self):
        from smart_search.security.crypto import fingerprint_secret

        a = fingerprint_secret("my-key")
        b = fingerprint_secret("my-key")
        assert a == b
        assert len(a) == 24

        c = fingerprint_secret("other-key")
        assert a != c

    def test_missing_master_key_fails_closed(self, monkeypatch):
        from smart_search.security.crypto import reset_master_fernet, encrypt_secret

        monkeypatch.delenv("SMART_SEARCH_MASTER_KEY", raising=False)
        monkeypatch.delenv("SMART_SEARCH_ALLOW_INSECURE_DEV_KEYS", raising=False)
        reset_master_fernet()

        with pytest.raises(RuntimeError, match="SMART_SEARCH_MASTER_KEY is required"):
            encrypt_secret("test-value")

        # Clean up
        reset_master_fernet()


# ---------------------------------------------------------------------------
# 4. Provider credential encryption and reveal
# ---------------------------------------------------------------------------

class TestProviderCredential:
    def test_create_credential_and_decrypt(self, session):
        from smart_search.storage.repositories import create_tenant, create_provider_credential
        from smart_search.security.crypto import encrypt_secret, decrypt_secret, fingerprint_secret

        tenant = create_tenant(session, name="T", slug="cred-test")
        raw_key = "sk-xai-12345"
        encrypted = encrypt_secret(raw_key)
        fp = fingerprint_secret(raw_key)

        cred = create_provider_credential(
            session,
            tenant_id=tenant.id,
            provider="xai-responses",
            encrypted_api_key=encrypted,
            key_fingerprint=fp,
        )
        assert cred.id
        assert cred.encrypted_api_key is not None
        assert cred.key_fingerprint == fp

        # Decrypt
        recovered = decrypt_secret(cred.encrypted_api_key)
        assert recovered == raw_key

    def test_get_active_credentials(self, session):
        from smart_search.storage.repositories import (
            create_tenant, create_provider_credential, get_active_credentials,
        )

        tenant = create_tenant(session, name="T", slug="cred-active")
        create_provider_credential(session, tenant_id=tenant.id, provider="exa")
        create_provider_credential(session, tenant_id=tenant.id, provider="context7")

        creds = get_active_credentials(session, tenant.id, "exa")
        assert len(creds) == 1
        assert creds[0].provider == "exa"


# ---------------------------------------------------------------------------
# 5. Provider config resolver
# ---------------------------------------------------------------------------

class TestConfigResolver:
    def test_local_resolver_returns_configured_providers(self, monkeypatch):
        from smart_search.runtime.config_resolver import LocalConfigResolver

        # Simulate a configured xAI key
        monkeypatch.setenv("XAI_API_KEY", "sk-test-xai-key")
        monkeypatch.setenv("EXA_API_KEY", "sk-test-exa-key")

        resolver = LocalConfigResolver()
        configs = resolver.resolve()

        providers = {c.provider for c in configs}
        assert "xai-responses" in providers
        assert "exa" in providers

        # Check fields
        xai = next(c for c in configs if c.provider == "xai-responses")
        assert xai.capability == "main_search"
        assert xai.api_key == "sk-test-xai-key"

    def test_cloud_resolver_reads_from_db(self, session, monkeypatch):
        from smart_search.storage.repositories import (
            create_tenant, create_provider_config, create_provider_credential,
        )
        from smart_search.security.crypto import encrypt_secret, fingerprint_secret
        from smart_search.runtime.config_resolver import CloudConfigResolver

        tenant = create_tenant(session, name="T", slug="resolver-test")
        raw_key = "sk-xai-resolver-key"
        encrypted = encrypt_secret(raw_key)
        fp = fingerprint_secret(raw_key)

        create_provider_credential(
            session,
            tenant_id=tenant.id,
            provider="xai-responses",
            encrypted_api_key=encrypted,
            key_fingerprint=fp,
            extra={"api_url": "https://api.x.ai/v1"},
        )
        create_provider_config(
            session,
            tenant_id=tenant.id,
            provider="xai-responses",
            capability="main_search",
            is_enabled=True,
            priority=10,
            settings={"model": "grok-3"},
        )

        resolver = CloudConfigResolver(session=session, tenant_id=tenant.id)
        configs = resolver.resolve()
        assert len(configs) >= 1

        xai = next(c for c in configs if c.provider == "xai-responses")
        assert xai.capability == "main_search"
        assert xai.api_key == raw_key
        assert xai.model == "grok-3"
        assert xai.api_url == "https://api.x.ai/v1"


# ---------------------------------------------------------------------------
# 6. ToolContext
# ---------------------------------------------------------------------------

class TestToolContext:
    def test_create_context(self):
        from smart_search.runtime.context import ToolContext

        ctx = ToolContext(
            request_id="req-001",
            tenant_id="t-001",
            user_id="u-001",
            token_id="tok-001",
            scopes=["search:read"],
            provider_config={"provider": "xai-responses"},
            metadata={"source": "api"},
        )
        assert ctx.request_id == "req-001"
        assert ctx.tenant_id == "t-001"
        assert "search:read" in ctx.scopes

    def test_context_defaults(self):
        from smart_search.runtime.context import ToolContext

        ctx = ToolContext(
            request_id="r2",
            tenant_id="t2",
            user_id="u2",
            token_id="tok2",
        )
        assert ctx.scopes == []
        assert ctx.metadata == {}


# ---------------------------------------------------------------------------
# 7. Permissions / scopes
# ---------------------------------------------------------------------------

class TestPermissions:
    def test_empty_scope_denies_cloud_access(self):
        from smart_search.auth.permissions import ScopeSet, PERM_SEARCH_READ

        ss = ScopeSet.from_dict(None)
        assert not ss.allows(PERM_SEARCH_READ)

    def test_explicit_permissions(self):
        from smart_search.auth.permissions import ScopeSet, PERM_SEARCH_READ, PERM_FETCH_READ

        ss = ScopeSet.from_dict({"permissions": ["search:read"]})
        assert ss.allows(PERM_SEARCH_READ)
        assert not ss.allows(PERM_FETCH_READ)

    def test_admin_grants_all(self):
        from smart_search.auth.permissions import ScopeSet, PERM_SEARCH_READ, PERM_FETCH_READ, PERM_ADMIN

        ss = ScopeSet.from_dict({"permissions": ["admin"]})
        assert ss.allows(PERM_SEARCH_READ)
        assert ss.allows(PERM_FETCH_READ)
        assert ss.allows(PERM_ADMIN)


# ---------------------------------------------------------------------------
# 8. Masking
# ---------------------------------------------------------------------------

class TestMasking:
    def test_mask_api_key(self):
        from smart_search.security.masking import mask_api_key

        assert mask_api_key(None) == "未配置"
        assert mask_api_key("") == "未配置"
        assert mask_api_key("sk_live_abc123") == "sk_l******c123"

    def test_mask_token(self):
        from smart_search.security.masking import mask_token

        assert mask_token(None) == "***"
        assert mask_token("short") == "***"
        assert mask_token("sk_live_abc123xyz789") == "sk_l…z789"


# ---------------------------------------------------------------------------
# 9. Provider factory
# ---------------------------------------------------------------------------

class TestProviderFactory:
    def test_create_xai_provider(self, monkeypatch):
        from smart_search.runtime.config_resolver import ResolvedToolConfig
        from smart_search.runtime.provider_factory import create_provider

        monkeypatch.setenv("XAI_API_KEY", "sk-test")
        rtc = ResolvedToolConfig(
            provider="xai-responses",
            capability="main_search",
            api_url="https://api.x.ai/v1",
            api_key="sk-test",
            model="grok-4-fast",
            tools=["web_search"],
        )
        provider = create_provider(rtc)
        assert provider.get_provider_name() == "xAI Responses"

    def test_create_exa_provider(self):
        from smart_search.runtime.config_resolver import ResolvedToolConfig
        from smart_search.runtime.provider_factory import create_provider

        rtc = ResolvedToolConfig(
            provider="exa",
            capability="docs_search",
            api_url="https://api.exa.ai",
            api_key="sk-exa-test",
        )
        provider = create_provider(rtc)
        assert provider.api_key == "sk-exa-test"

    def test_create_context7_provider(self):
        from smart_search.runtime.config_resolver import ResolvedToolConfig
        from smart_search.runtime.provider_factory import create_provider

        rtc = ResolvedToolConfig(
            provider="context7",
            capability="docs_search",
            api_url="https://context7.com",
            api_key="sk-c7",
        )
        provider = create_provider(rtc)
        assert provider.api_url == "https://context7.com"

    def test_create_zhipu_provider(self):
        from smart_search.runtime.config_resolver import ResolvedToolConfig
        from smart_search.runtime.provider_factory import create_provider

        rtc = ResolvedToolConfig(
            provider="zhipu",
            capability="web_search",
            api_url="https://open.bigmodel.cn/api",
            api_key="sk-zhipu",
        )
        provider = create_provider(rtc)
        assert provider.api_key == "sk-zhipu"

    def test_create_openai_compatible_provider(self):
        from smart_search.runtime.config_resolver import ResolvedToolConfig
        from smart_search.runtime.provider_factory import create_provider

        rtc = ResolvedToolConfig(
            provider="openai-compatible",
            capability="main_search",
            api_url="https://api.openai.com/v1",
            api_key="sk-oai",
            model="gpt-4o",
        )
        provider = create_provider(rtc)
        assert provider.api_url == "https://api.openai.com/v1"

    def test_unknown_provider_raises(self):
        from smart_search.runtime.config_resolver import ResolvedToolConfig
        from smart_search.runtime.provider_factory import create_provider

        rtc = ResolvedToolConfig(
            provider="unknown",
            capability="test",
            api_url="https://example.com",
            api_key="key",
        )
        with pytest.raises(ValueError, match="Unknown provider"):
            create_provider(rtc)


# ---------------------------------------------------------------------------
# 10. Audit event
# ---------------------------------------------------------------------------

class TestAudit:
    def test_log_audit(self, session):
        from smart_search.storage.repositories import create_tenant
        from smart_search.security.audit import log_audit
        from smart_search.storage.models import AuditEvent

        tenant = create_tenant(session, name="T", slug="audit-test")
        log_audit(session, tenant_id=tenant.id, action="token.create", actor_id="u1")
        session.flush()

        from sqlalchemy import select
        events = session.execute(select(AuditEvent)).scalars().all()
        assert len(events) >= 1
        assert events[0].action == "token.create"

    def test_log_audit_redacts_secret_details(self, session):
        from sqlalchemy import select

        from smart_search.storage.models import AuditEvent
        from smart_search.storage.repositories import create_tenant
        from smart_search.security.audit import log_audit

        tenant = create_tenant(session, name="T", slug="audit-redact")
        log_audit(
            session,
            tenant_id=tenant.id,
            action="provider.reveal",
            detail={"api_key": "sk-secret", "nested": {"authorization": "Bearer abc"}, "safe": "ok"},
        )
        session.flush()

        event = session.execute(select(AuditEvent)).scalars().one()
        assert event.detail["api_key"] == "[redacted]"
        assert event.detail["nested"]["authorization"] == "[redacted]"
        assert event.detail["safe"] == "ok"
