"""Task API routes – Deep Research start, status, control, retry/redo.

All endpoints require Bearer auth with appropriate scopes:
- deep:read or admin for read operations
- deep:write or admin for mutation operations
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from ..auth.permissions import ScopeSet
from ..runtime.context import ToolContext
from .dependencies import require_bearer

_logger = logging.getLogger(__name__)


class DeepStartRequest(BaseModel):
    topic: str
    depth: str = Field(default="standard", alias="depth")
    max_sources: int = Field(default=5, alias="max_sources")

    model_config = {"populate_by_name": True}


def _require_deep_read(request: Request) -> ToolContext:
    """Check deep:read or admin permission."""
    ctx = getattr(request.state, "tool_context", None)
    if ctx is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    scope_set = ScopeSet(permissions=frozenset(ctx.scopes))
    if not scope_set.allows("deep:read") and not scope_set.allows("admin"):
        raise HTTPException(status_code=403, detail="Token lacks deep:read or admin scope")
    return ctx


def _require_deep_write(request: Request) -> ToolContext:
    """Check deep:write or admin permission."""
    ctx = getattr(request.state, "tool_context", None)
    if ctx is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    scope_set = ScopeSet(permissions=frozenset(ctx.scopes))
    if not scope_set.allows("deep:write") and not scope_set.allows("admin"):
        raise HTTPException(status_code=403, detail="Token lacks deep:write or admin scope")
    return ctx


def create_task_router() -> APIRouter:
    router = APIRouter(prefix="/api/tasks", tags=["tasks"])

    @router.post("/deep_start")
    async def deep_start(
        body: DeepStartRequest,
        request: Request,
        ctx: ToolContext = Depends(require_bearer),
    ) -> dict[str, Any]:
        """Start a deep research task. Returns task_id immediately."""
        _require_deep_read(request)
        # Also require deep:write to start
        _require_deep_write(request)

        session = request.state.db_session
        from ..tasks.queue import DBBackedQueue

        queue = DBBackedQueue(session)
        result = queue.enqueue_deep_research(
            tenant_id=ctx.tenant_id,
            topic=body.topic,
            depth=body.depth,
            max_sources=body.max_sources,
            user_id=ctx.user_id,
        )
        tr = result["task_run"]

        return {
            "task_id": tr.id,
            "status": tr.status,
            "topic": tr.topic,
            "task_type": tr.task_type,
            "created_at": tr.created_at.isoformat() if tr.created_at else None,
        }

    @router.get("")
    async def list_tasks(
        request: Request,
        ctx: ToolContext = Depends(require_bearer),
    ) -> dict[str, Any]:
        """List task runs for the current tenant."""
        _require_deep_read(request)
        session = request.state.db_session
        from ..storage.repositories import list_task_runs

        tasks = list_task_runs(session, ctx.tenant_id)
        return {
            "tasks": [
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
        }

    @router.get("/{task_id}/status")
    async def task_status(
        task_id: str,
        request: Request,
        ctx: ToolContext = Depends(require_bearer),
    ) -> dict[str, Any]:
        """Get task status and node overview."""
        _require_deep_read(request)
        session = request.state.db_session
        from ..storage.repositories import get_task_run, list_task_nodes

        tr = get_task_run(session, task_id)
        if tr is None or tr.tenant_id != ctx.tenant_id:
            raise HTTPException(status_code=404, detail="Task not found")

        nodes = list_task_nodes(session, task_id)
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
            "created_at": tr.created_at.isoformat() if tr.created_at else None,
            "updated_at": tr.updated_at.isoformat() if tr.updated_at else None,
        }

    @router.get("/{task_id}/events")
    async def task_events(
        task_id: str,
        request: Request,
        ctx: ToolContext = Depends(require_bearer),
    ) -> dict[str, Any]:
        """Get task event log."""
        _require_deep_read(request)
        session = request.state.db_session
        from ..storage.repositories import get_task_run, list_task_events

        tr = get_task_run(session, task_id)
        if tr is None or tr.tenant_id != ctx.tenant_id:
            raise HTTPException(status_code=404, detail="Task not found")

        events = list_task_events(session, task_id)
        return {
            "task_id": tr.id,
            "events": [
                {
                    "id": e.id,
                    "node_id": e.node_id,
                    "event_type": e.event_type,
                    "message": e.message,
                    "detail": e.detail,
                    "created_at": e.created_at.isoformat() if e.created_at else None,
                }
                for e in events
            ],
        }

    @router.get("/{task_id}/result")
    async def task_result(
        task_id: str,
        request: Request,
        ctx: ToolContext = Depends(require_bearer),
    ) -> dict[str, Any]:
        """Get task result and artifacts."""
        _require_deep_read(request)
        session = request.state.db_session
        from ..storage.repositories import get_task_run, list_task_artifacts

        tr = get_task_run(session, task_id)
        if tr is None or tr.tenant_id != ctx.tenant_id:
            raise HTTPException(status_code=404, detail="Task not found")

        artifacts = list_task_artifacts(session, task_id)
        return {
            "id": tr.id,
            "status": tr.status,
            "result": tr.result,
            "error": tr.error,
            "artifacts": [
                {
                    "id": a.id,
                    "name": a.name,
                    "artifact_type": a.artifact_type,
                    "content": a.content,
                }
                for a in artifacts
            ],
        }

    @router.post("/{task_id}/pause")
    async def pause_task(
        task_id: str,
        request: Request,
        ctx: ToolContext = Depends(require_bearer),
    ) -> dict[str, Any]:
        """Pause a running/queued task."""
        _require_deep_write(request)
        session = request.state.db_session
        from ..storage.repositories import get_task_run
        from ..tasks.queue import DBBackedQueue

        tr = get_task_run(session, task_id)
        if tr is None or tr.tenant_id != ctx.tenant_id:
            raise HTTPException(status_code=404, detail="Task not found")

        queue = DBBackedQueue(session)
        queue.pause_task(task_id)
        return {"task_id": task_id, "status": "paused"}

    @router.post("/{task_id}/resume")
    async def resume_task(
        task_id: str,
        request: Request,
        ctx: ToolContext = Depends(require_bearer),
    ) -> dict[str, Any]:
        """Resume a paused task."""
        _require_deep_write(request)
        session = request.state.db_session
        from ..storage.repositories import get_task_run
        from ..tasks.queue import DBBackedQueue

        tr = get_task_run(session, task_id)
        if tr is None or tr.tenant_id != ctx.tenant_id:
            raise HTTPException(status_code=404, detail="Task not found")

        queue = DBBackedQueue(session)
        queue.resume_task(task_id)
        return {"task_id": task_id, "status": "queued"}

    @router.post("/{task_id}/cancel")
    async def cancel_task(
        task_id: str,
        request: Request,
        ctx: ToolContext = Depends(require_bearer),
    ) -> dict[str, Any]:
        """Cancel a task."""
        _require_deep_write(request)
        session = request.state.db_session
        from ..storage.repositories import get_task_run
        from ..tasks.queue import DBBackedQueue

        tr = get_task_run(session, task_id)
        if tr is None or tr.tenant_id != ctx.tenant_id:
            raise HTTPException(status_code=404, detail="Task not found")

        queue = DBBackedQueue(session)
        queue.cancel_task(task_id)
        return {"task_id": task_id, "status": "cancelled"}

    @router.post("/nodes/{node_id}/retry")
    async def retry_node(
        node_id: str,
        request: Request,
        ctx: ToolContext = Depends(require_bearer),
    ) -> dict[str, Any]:
        """Retry a failed node."""
        _require_deep_write(request)
        session = request.state.db_session
        from ..storage.repositories import get_task_node, retry_node as repo_retry_node, get_task_run

        node = get_task_node(session, node_id)
        if node is None:
            raise HTTPException(status_code=404, detail="Node not found")

        # Verify tenant access via task_run
        tr = get_task_run(session, node.task_run_id)
        if tr is None or tr.tenant_id != ctx.tenant_id:
            raise HTTPException(status_code=404, detail="Node not found")

        updated = repo_retry_node(session, node_id)
        return {"node_id": node_id, "status": updated.status if updated else "error"}

    @router.post("/nodes/{node_id}/redo")
    async def redo_node(
        node_id: str,
        request: Request,
        ctx: ToolContext = Depends(require_bearer),
    ) -> dict[str, Any]:
        """Redo a node and mark downstream dependents as stale."""
        _require_deep_write(request)
        session = request.state.db_session
        from ..storage.repositories import (
            get_task_node, redo_node_mark_downstream_stale, get_task_run,
        )

        node = get_task_node(session, node_id)
        if node is None:
            raise HTTPException(status_code=404, detail="Node not found")

        tr = get_task_run(session, node.task_run_id)
        if tr is None or tr.tenant_id != ctx.tenant_id:
            raise HTTPException(status_code=404, detail="Node not found")

        affected = redo_node_mark_downstream_stale(session, node_id)
        return {"node_id": node_id, "affected_nodes": affected}

    return router
