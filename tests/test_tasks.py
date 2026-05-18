"""Task system tests – DAG creation, deep_start API, status/events/result,
pause/resume/cancel, retry/redo nodes, worker run_once, permissions.

All tests use in-memory/tmp SQLite. No network.
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

    from smart_search.security.crypto import reset_master_fernet
    reset_master_fernet()

    monkeypatch.setenv("SMART_SEARCH_MASTER_KEY", "test-master-key-for-task-tests")
    monkeypatch.setenv("SMART_SEARCH_TOKEN_SECRET", "test-token-secret-for-tasks")
    monkeypatch.setenv("SMART_SEARCH_ALLOW_INSECURE_DEV_KEYS", "true")


@pytest.fixture()
def db_engine(tmp_path):
    from sqlalchemy import create_engine
    from smart_search.storage.models import Base
    from smart_search.storage.db import create_session_factory, init_db

    db_path = tmp_path / "test-tasks.db"
    url = f"sqlite:///{db_path}"
    engine = create_engine(url, connect_args={"check_same_thread": False})
    init_db(engine)
    yield engine
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


@pytest.fixture()
def session(db_engine):
    from smart_search.storage.db import create_session_factory

    SessionFactory = create_session_factory(db_engine)
    sess = SessionFactory()
    yield sess
    sess.commit()
    sess.close()


@pytest.fixture()
def session_factory(db_engine):
    from smart_search.storage.db import create_session_factory
    return create_session_factory(db_engine)


@pytest.fixture()
def tenant_and_user(session):
    from smart_search.storage.repositories import create_tenant, create_user, add_membership

    tenant = create_tenant(session, name="TaskTestOrg", slug="tasktest")
    user = create_user(session, email="taskuser@test.com")
    add_membership(session, tenant_id=tenant.id, user_id=user.id, role="admin")
    session.commit()
    return tenant, user


@pytest.fixture()
def app_and_client(tmp_path):
    from sqlalchemy import create_engine
    from smart_search.storage.models import Base
    from smart_search.storage.db import create_session_factory, init_db
    from smart_search.server.app import create_app

    db_path = tmp_path / "test-task-api.db"
    url = f"sqlite:///{db_path}"
    engine = create_engine(url, connect_args={"check_same_thread": False})
    init_db(engine)
    sf = create_session_factory(engine)
    app = create_app(engine=engine, session_factory=sf)

    from starlette.testclient import TestClient
    client = TestClient(app)

    yield app, client, engine, sf

    Base.metadata.drop_all(bind=engine)
    engine.dispose()


@pytest.fixture()
def admin_token(app_and_client):
    _, client, engine, sf = app_and_client

    from smart_search.auth.tokens import generate_token, hash_token, token_prefix
    from smart_search.storage.repositories import (
        create_tenant, create_user, add_membership, store_api_token,
    )

    sess = sf()
    tenant = create_tenant(sess, name="TaskAPITestOrg", slug="taskapi")
    user = create_user(sess, email="taskadmin@test.com")
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
        name="admin-task-token",
        scopes={"permissions": ["admin"]},
    )
    sess.commit()
    sess.close()

    return raw, db_token, tenant, user


@pytest.fixture()
def deep_read_write_token(app_and_client):
    """Token with deep:read and deep:write but not admin."""
    _, client, engine, sf = app_and_client

    from smart_search.auth.tokens import generate_token, hash_token, token_prefix
    from smart_search.storage.repositories import (
        create_tenant, create_user, store_api_token,
    )

    sess = sf()
    tenant = create_tenant(sess, name="DeepRWOrg", slug="deeprw")
    user = create_user(sess, email="deeprw@test.com")
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
        name="deep-rw-token",
        scopes={"permissions": ["deep:read", "deep:write"]},
    )
    sess.commit()
    sess.close()

    return raw, db_token, tenant, user


@pytest.fixture()
def readonly_token(app_and_client):
    """Token with only search:read (no deep permissions)."""
    _, client, engine, sf = app_and_client

    from smart_search.auth.tokens import generate_token, hash_token, token_prefix
    from smart_search.storage.repositories import (
        create_tenant, create_user, store_api_token,
    )

    sess = sf()
    tenant = create_tenant(sess, name="ReadOnlyOrg", slug="readonly")
    user = create_user(sess, email="readonly@test.com")
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
        name="readonly-token",
        scopes={"permissions": ["search:read"]},
    )
    sess.commit()
    sess.close()

    return raw, db_token, tenant


# ---------------------------------------------------------------------------
# 1. DAG creation
# ---------------------------------------------------------------------------

class TestDAGCreation:
    def test_build_deep_research_dag(self):
        from smart_search.tasks.deep import build_deep_research_dag

        nodes = build_deep_research_dag("test topic", depth="standard", max_sources=5)
        assert len(nodes) == 5
        keys = [n["key"] for n in nodes]
        assert "plan" in keys
        assert "search" in keys
        assert "fetch" in keys
        assert "synthesize" in keys
        assert "finalize" in keys

        # Verify DAG structure: plan has no deps, search depends on plan, etc.
        plan = next(n for n in nodes if n["key"] == "plan")
        assert plan["depends_on"] == []
        search = next(n for n in nodes if n["key"] == "search")
        assert "plan" in search["depends_on"]
        fetch = next(n for n in nodes if n["key"] == "fetch")
        assert "search" in fetch["depends_on"]

    def test_enqueue_creates_task_run_and_nodes(self, session, tenant_and_user):
        tenant, user = tenant_and_user
        from smart_search.tasks.queue import DBBackedQueue

        queue = DBBackedQueue(session)
        result = queue.enqueue_deep_research(
            tenant_id=tenant.id,
            topic="How does RAG work?",
            depth="standard",
            max_sources=5,
            user_id=user.id,
        )

        tr = result["task_run"]
        assert tr.id
        assert tr.status == "queued"
        assert tr.topic == "How does RAG work?"
        assert tr.task_type == "deep_research"
        assert tr.tenant_id == tenant.id

        from smart_search.storage.repositories import list_task_nodes
        nodes = list_task_nodes(session, tr.id)
        assert len(nodes) == 5

        # Verify events were created
        from smart_search.storage.repositories import list_task_events
        events = list_task_events(session, tr.id)
        assert len(events) >= 1
        assert events[0].event_type == "created"


# ---------------------------------------------------------------------------
# 2. Task CRUD
# ---------------------------------------------------------------------------

class TestTaskCRUD:
    def test_create_and_get_task_run(self, session, tenant_and_user):
        tenant, user = tenant_and_user
        from smart_search.storage.repositories import create_task_run, get_task_run

        tr = create_task_run(session, tenant_id=tenant.id, topic="test", user_id=user.id)
        assert tr.id

        found = get_task_run(session, tr.id)
        assert found is not None
        assert found.topic == "test"

    def test_list_task_runs(self, session, tenant_and_user):
        tenant, user = tenant_and_user
        from smart_search.storage.repositories import create_task_run, list_task_runs

        create_task_run(session, tenant_id=tenant.id, topic="t1")
        create_task_run(session, tenant_id=tenant.id, topic="t2")
        runs = list_task_runs(session, tenant.id)
        assert len(runs) == 2

    def test_update_task_status(self, session, tenant_and_user):
        tenant, user = tenant_and_user
        from smart_search.storage.repositories import create_task_run, update_task_status, get_task_run

        tr = create_task_run(session, tenant_id=tenant.id, topic="test")
        update_task_status(session, tr.id, "running")
        found = get_task_run(session, tr.id)
        assert found.status == "running"

    def test_append_and_list_events(self, session, tenant_and_user):
        tenant, user = tenant_and_user
        from smart_search.storage.repositories import create_task_run, append_task_event, list_task_events

        tr = create_task_run(session, tenant_id=tenant.id, topic="test")
        append_task_event(session, task_run_id=tr.id, event_type="info", message="hello")
        append_task_event(session, task_run_id=tr.id, event_type="error", message="oops")
        events = list_task_events(session, tr.id)
        assert len(events) == 2
        assert events[0].message == "hello"
        assert events[1].message == "oops"

    def test_create_and_list_artifacts(self, session, tenant_and_user):
        tenant, user = tenant_and_user
        from smart_search.storage.repositories import create_task_run, create_artifact, list_task_artifacts

        tr = create_task_run(session, tenant_id=tenant.id, topic="test")
        create_artifact(session, task_run_id=tr.id, name="result.json", content={"answer": "42"})
        artifacts = list_task_artifacts(session, tr.id)
        assert len(artifacts) == 1
        assert artifacts[0].content == {"answer": "42"}


# ---------------------------------------------------------------------------
# 3. Node retry / redo
# ---------------------------------------------------------------------------

class TestNodeRetryRedo:
    def test_retry_node(self, session, tenant_and_user):
        tenant, user = tenant_and_user
        from smart_search.storage.repositories import (
            create_task_run, create_task_node, retry_node, get_task_node,
        )

        tr = create_task_run(session, tenant_id=tenant.id, topic="test")
        node = create_task_node(
            session, task_run_id=tr.id, node_type="search", name="Search",
            status="failed",
        )
        updated = retry_node(session, node.id)
        assert updated.status == "pending"
        assert updated.attempt_count == 1

        fresh = get_task_node(session, node.id)
        assert fresh.status == "pending"

    def test_redo_node_mark_downstream_stale(self, session, tenant_and_user):
        tenant, user = tenant_and_user
        from smart_search.storage.repositories import (
            create_task_run, create_task_node, redo_node_mark_downstream_stale,
            list_task_nodes, get_task_node,
        )

        tr = create_task_run(session, tenant_id=tenant.id, topic="test")
        plan = create_task_node(
            session, task_run_id=tr.id, node_type="plan", name="Plan",
            status="completed",
        )
        search = create_task_node(
            session, task_run_id=tr.id, node_type="search", name="Search",
            depends_on=[plan.id], status="completed",
        )
        fetch = create_task_node(
            session, task_run_id=tr.id, node_type="fetch", name="Fetch",
            depends_on=[search.id], status="completed",
        )

        # Redo "search" node: search -> pending, fetch -> stale
        affected = redo_node_mark_downstream_stale(session, search.id)
        assert search.id in affected
        assert fetch.id in affected
        assert plan.id not in affected

        search_fresh = get_task_node(session, search.id)
        assert search_fresh.status == "pending"

        fetch_fresh = get_task_node(session, fetch.id)
        assert fetch_fresh.status == "stale"

        plan_fresh = get_task_node(session, plan.id)
        assert plan_fresh.status == "completed"  # unchanged


# ---------------------------------------------------------------------------
# 4. Task API tests
# ---------------------------------------------------------------------------

class TestTaskAPI:
    def test_deep_start_returns_task_id(self, app_and_client, admin_token):
        _, client, _, _ = app_and_client
        raw, _, _, _ = admin_token

        resp = client.post(
            "/api/tasks/deep_start",
            json={"topic": "What is quantum computing?"},
            headers={"Authorization": f"Bearer {raw}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "task_id" in data
        assert data["status"] == "queued"
        assert data["topic"] == "What is quantum computing?"

    def test_list_tasks(self, app_and_client, admin_token):
        _, client, _, _ = app_and_client
        raw, _, _, _ = admin_token

        # Create a task first
        resp = client.post(
            "/api/tasks/deep_start",
            json={"topic": "test list"},
            headers={"Authorization": f"Bearer {raw}"},
        )
        assert resp.status_code == 200

        resp = client.get(
            "/api/tasks",
            headers={"Authorization": f"Bearer {raw}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "tasks" in data
        assert len(data["tasks"]) >= 1

    def test_task_status(self, app_and_client, admin_token):
        _, client, _, _ = app_and_client
        raw, _, _, _ = admin_token

        resp = client.post(
            "/api/tasks/deep_start",
            json={"topic": "test status"},
            headers={"Authorization": f"Bearer {raw}"},
        )
        task_id = resp.json()["task_id"]

        resp = client.get(
            f"/api/tasks/{task_id}/status",
            headers={"Authorization": f"Bearer {raw}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == task_id
        assert "nodes" in data
        assert len(data["nodes"]) == 5

    def test_task_events(self, app_and_client, admin_token):
        _, client, _, _ = app_and_client
        raw, _, _, _ = admin_token

        resp = client.post(
            "/api/tasks/deep_start",
            json={"topic": "test events"},
            headers={"Authorization": f"Bearer {raw}"},
        )
        task_id = resp.json()["task_id"]

        resp = client.get(
            f"/api/tasks/{task_id}/events",
            headers={"Authorization": f"Bearer {raw}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["events"]) >= 1

    def test_task_result(self, app_and_client, admin_token):
        _, client, _, _ = app_and_client
        raw, _, _, _ = admin_token

        resp = client.post(
            "/api/tasks/deep_start",
            json={"topic": "test result"},
            headers={"Authorization": f"Bearer {raw}"},
        )
        task_id = resp.json()["task_id"]

        resp = client.get(
            f"/api/tasks/{task_id}/result",
            headers={"Authorization": f"Bearer {raw}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == task_id
        assert "artifacts" in data

    def test_pause_resume_cancel(self, app_and_client, admin_token):
        _, client, _, _ = app_and_client
        raw, _, _, _ = admin_token

        resp = client.post(
            "/api/tasks/deep_start",
            json={"topic": "test pause"},
            headers={"Authorization": f"Bearer {raw}"},
        )
        task_id = resp.json()["task_id"]

        # Pause
        resp = client.post(
            f"/api/tasks/{task_id}/pause",
            headers={"Authorization": f"Bearer {raw}"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "paused"

        # Verify status
        resp = client.get(
            f"/api/tasks/{task_id}/status",
            headers={"Authorization": f"Bearer {raw}"},
        )
        assert resp.json()["status"] == "paused"

        # Resume
        resp = client.post(
            f"/api/tasks/{task_id}/resume",
            headers={"Authorization": f"Bearer {raw}"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "queued"

        # Cancel
        resp = client.post(
            f"/api/tasks/{task_id}/cancel",
            headers={"Authorization": f"Bearer {raw}"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "cancelled"

    def test_retry_node_api(self, app_and_client, admin_token):
        _, client, _, _ = app_and_client
        raw, _, tenant, _ = admin_token

        from smart_search.storage.repositories import create_task_run, create_task_node
        from smart_search.storage.db import create_session_factory
        from smart_search.server.app import create_app

        # We need to create a failed node in DB directly
        sf = app_and_client[3]
        sess = sf()
        tr = create_task_run(sess, tenant_id=tenant.id, topic="retry-test")
        node = create_task_node(
            sess, task_run_id=tr.id, node_type="search", name="Search",
            status="failed",
        )
        sess.commit()
        sess.close()

        resp = client.post(
            f"/api/tasks/nodes/{node.id}/retry",
            headers={"Authorization": f"Bearer {raw}"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "pending"

    def test_redo_node_api(self, app_and_client, admin_token):
        _, client, _, sf = app_and_client
        raw, _, tenant, _ = admin_token

        from smart_search.storage.repositories import create_task_run, create_task_node

        sess = sf()
        tr = create_task_run(sess, tenant_id=tenant.id, topic="redo-test")
        plan = create_task_node(
            sess, task_run_id=tr.id, node_type="plan", name="Plan", status="completed",
        )
        search = create_task_node(
            sess, task_run_id=tr.id, node_type="search", name="Search",
            depends_on=[plan.id], status="completed",
        )
        fetch = create_task_node(
            sess, task_run_id=tr.id, node_type="fetch", name="Fetch",
            depends_on=[search.id], status="completed",
        )
        sess.commit()
        sess.close()

        resp = client.post(
            f"/api/tasks/nodes/{search.id}/redo",
            headers={"Authorization": f"Bearer {raw}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert search.id in data["affected_nodes"]
        assert fetch.id in data["affected_nodes"]


# ---------------------------------------------------------------------------
# 5. Worker run_once
# ---------------------------------------------------------------------------

class TestWorker:
    def test_worker_run_once_success(self, db_engine, session_factory, tenant_and_user):
        tenant, user = tenant_and_user

        from smart_search.tasks.queue import DBBackedQueue
        from smart_search.tasks.worker import TaskWorker
        from smart_search.tasks.deep import register_node_executor
        from smart_search.storage.repositories import get_task_run

        # Monkeypatch all node executors to succeed
        executed_nodes = []

        def _stub_executor(node, ctx):
            executed_nodes.append(node.node_type if hasattr(node, "node_type") else node.get("node_type"))
            return {"ok": True, "stub": True}

        for ntype in ("plan", "search", "fetch", "synthesize", "finalize"):
            register_node_executor(ntype, _stub_executor)

        # Enqueue a task
        sess = session_factory()
        queue = DBBackedQueue(sess)
        result = queue.enqueue_deep_research(
            tenant_id=tenant.id, topic="worker test", depth="standard", max_sources=5,
        )
        task_id = result["task_run"].id
        sess.commit()
        sess.close()

        # Run the worker
        worker = TaskWorker(session_factory, worker_id="test-worker")
        processed = worker.run_once()
        assert processed is True

        # Verify all nodes executed
        assert len(executed_nodes) == 5
        assert "plan" in executed_nodes
        assert "finalize" in executed_nodes

        # Verify task completed
        sess = session_factory()
        tr = get_task_run(sess, task_id)
        assert tr.status == "completed"
        sess.close()

    def test_worker_nothing_to_process(self, db_engine, session_factory):
        from smart_search.tasks.worker import TaskWorker

        worker = TaskWorker(session_factory, worker_id="test-worker")
        processed = worker.run_once()
        assert processed is False


# ---------------------------------------------------------------------------
# 6. Permission tests
# ---------------------------------------------------------------------------

class TestTaskPermissions:
    def test_readonly_token_403_on_deep_start(self, app_and_client, readonly_token):
        _, client, _, _ = app_and_client
        raw, _, _ = readonly_token

        resp = client.post(
            "/api/tasks/deep_start",
            json={"topic": "should fail"},
            headers={"Authorization": f"Bearer {raw}"},
        )
        assert resp.status_code == 403

    def test_readonly_token_403_on_status(self, app_and_client, readonly_token):
        _, client, _, _ = app_and_client
        raw, _, _ = readonly_token

        resp = client.get(
            "/api/tasks",
            headers={"Authorization": f"Bearer {raw}"},
        )
        assert resp.status_code == 403

    def test_deep_rw_token_can_start(self, app_and_client, deep_read_write_token):
        _, client, _, _ = app_and_client
        raw, _, _, _ = deep_read_write_token

        resp = client.post(
            "/api/tasks/deep_start",
            json={"topic": "deep rw test"},
            headers={"Authorization": f"Bearer {raw}"},
        )
        assert resp.status_code == 200

    def test_deep_rw_token_can_pause(self, app_and_client, deep_read_write_token):
        _, client, _, _ = app_and_client
        raw, _, _, _ = deep_read_write_token

        resp = client.post(
            "/api/tasks/deep_start",
            json={"topic": "pause test"},
            headers={"Authorization": f"Bearer {raw}"},
        )
        task_id = resp.json()["task_id"]

        resp = client.post(
            f"/api/tasks/{task_id}/pause",
            headers={"Authorization": f"Bearer {raw}"},
        )
        assert resp.status_code == 200

    def test_no_auth_401(self, app_and_client):
        _, client, _, _ = app_and_client
        resp = client.get("/api/tasks")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# 7. Admin Tasks page
# ---------------------------------------------------------------------------

class TestAdminTasksPage:
    def test_tasks_page(self, app_and_client, admin_token):
        _, client, _, _ = app_and_client
        raw, _, _, _ = admin_token

        resp = client.get("/admin/tasks", headers={"Authorization": f"Bearer {raw}"})
        assert resp.status_code == 200
        assert "Tasks" in resp.text or "任务" in resp.text

    def test_admin_task_list_api(self, app_and_client, admin_token):
        _, client, _, _ = app_and_client
        raw, _, _, _ = admin_token

        resp = client.get("/admin/api/tasks", headers={"Authorization": f"Bearer {raw}"})
        assert resp.status_code == 200

    def test_admin_pause_cancel_via_api(self, app_and_client, admin_token):
        _, client, _, _ = app_and_client
        raw, _, tenant, _ = admin_token

        # Start a task via deep_start
        resp = client.post(
            "/api/tasks/deep_start",
            json={"topic": "admin cancel test"},
            headers={"Authorization": f"Bearer {raw}"},
        )
        task_id = resp.json()["task_id"]

        # Pause via admin API
        resp = client.post(
            f"/admin/api/tasks/{task_id}/pause",
            headers={"Authorization": f"Bearer {raw}"},
        )
        assert resp.status_code == 200

        # Cancel via admin API
        resp = client.post(
            f"/admin/api/tasks/{task_id}/cancel",
            headers={"Authorization": f"Bearer {raw}"},
        )
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# 8. States module
# ---------------------------------------------------------------------------

class TestStates:
    def test_task_status_constants(self):
        from smart_search.tasks.states import TaskStatus

        assert TaskStatus.QUEUED == "queued"
        assert TaskStatus.RUNNING == "running"
        assert TaskStatus.COMPLETED == "completed"
        assert TaskStatus.FAILED == "failed"
        assert TaskStatus.CANCELLED == "cancelled"
        assert TaskStatus.PAUSED == "paused"
        assert "queued" in TaskStatus.ALL

    def test_node_status_constants(self):
        from smart_search.tasks.states import NodeStatus

        assert NodeStatus.PENDING == "pending"
        assert NodeStatus.READY == "ready"
        assert NodeStatus.RUNNING == "running"
        assert NodeStatus.STALE == "stale"
        assert NodeStatus.COMPLETED == "completed"
        assert "stale" in NodeStatus.ALL


# ---------------------------------------------------------------------------
# 9. Execute node with monkeypatch
# ---------------------------------------------------------------------------

class TestExecuteNode:
    def test_execute_node_with_registered_executor(self):
        from smart_search.tasks.deep import execute_node, register_node_executor

        called = []

        def my_executor(node, ctx):
            called.append("yes")
            return {"ok": True, "custom": True}

        register_node_executor("plan", my_executor)

        class FakeNode:
            node_type = "plan"
            id = "fake-id"

        result = execute_node(FakeNode(), ctx=None)
        assert called == ["yes"]
        assert result["custom"] is True

        # Clean up
        register_node_executor("plan", None)

    def test_default_execute_no_network(self):
        from smart_search.tasks.deep import execute_node

        class FakeNode:
            node_type = "search"
            id = "fake-search-id"

        result = execute_node(FakeNode(), ctx=None)
        assert result["ok"] is True
        assert "stub" in result
