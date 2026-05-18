"""DB-backed task queue – enqueue, claim, complete, fail.

Designed for SQLite first; PostgreSQL can add SKIP LOCKED later.
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.orm import Session

from .states import TaskStatus, NodeStatus

_logger = logging.getLogger(__name__)


class DBBackedQueue:
    """Simple DB-backed queue using status field transitions."""

    def __init__(self, session: Session) -> None:
        self.session = session

    # ---- Enqueue ----------------------------------------------------------

    def enqueue_deep_research(
        self,
        *,
        tenant_id: str,
        topic: str,
        depth: str = "standard",
        max_sources: int = 5,
        user_id: str | None = None,
    ) -> dict[str, Any]:
        """Create a deep research task run with its full DAG.

        Returns a dict with task_run and nodes for immediate API response.
        """
        from ..storage.repositories import (
            create_task_run,
            create_task_node,
            append_task_event,
        )
        from .deep import build_deep_research_dag

        # Create the task run
        params = {"depth": depth, "max_sources": max_sources}
        tr = create_task_run(
            self.session,
            tenant_id=tenant_id,
            task_type="deep_research",
            topic=topic,
            user_id=user_id,
            params=params,
            status=TaskStatus.QUEUED,
        )

        # Build the DAG nodes
        dag_nodes = build_deep_research_dag(topic, depth=depth, max_sources=max_sources)
        node_map: dict[str, str] = {}  # key -> db id

        for n in dag_nodes:
            # Resolve depends_on keys to actual IDs (first pass uses keys)
            dep_ids = [node_map[d] for d in n.get("depends_on", []) if d in node_map]
            tn = create_task_node(
                self.session,
                task_run_id=tr.id,
                node_type=n["node_type"],
                name=n["name"],
                depends_on=dep_ids if dep_ids else None,
                config=n.get("config"),
                status=n.get("status", NodeStatus.PENDING),
            )
            node_map[n["key"]] = tn.id

        # Second pass: update depends_on with resolved IDs for nodes that depend on later nodes
        # (already handled by ordering above)

        append_task_event(
            self.session,
            task_run_id=tr.id,
            event_type="created",
            message=f"Deep research task created: {topic}",
            detail={"depth": depth, "max_sources": max_sources},
        )

        return {
            "task_run": tr,
            "nodes": dag_nodes,
            "node_map": node_map,
        }

    # ---- Claim / complete / fail ------------------------------------------

    def claim_next_task(self, worker_id: str = "default") -> Any | None:
        """Claim the next queued task (sets status to running)."""
        from ..storage.repositories import claim_next_task

        return claim_next_task(self.session, worker_id=worker_id)

    def complete_task(self, task_id: str, result: dict | None = None) -> None:
        from ..storage.repositories import update_task_status, append_task_event

        update_task_status(self.session, task_id, TaskStatus.COMPLETED, result=result)
        append_task_event(
            self.session,
            task_run_id=task_id,
            event_type="completed",
            message="Task completed",
        )

    def fail_task(self, task_id: str, error: str = "") -> None:
        from ..storage.repositories import update_task_status, append_task_event

        update_task_status(self.session, task_id, TaskStatus.FAILED, error=error)
        append_task_event(
            self.session,
            task_run_id=task_id,
            event_type="failed",
            message=f"Task failed: {error}",
        )

    def pause_task(self, task_id: str) -> None:
        from ..storage.repositories import update_task_status, append_task_event

        update_task_status(self.session, task_id, TaskStatus.PAUSED)
        append_task_event(
            self.session,
            task_run_id=task_id,
            event_type="paused",
            message="Task paused",
        )

    def resume_task(self, task_id: str) -> None:
        from ..storage.repositories import update_task_status, append_task_event

        update_task_status(self.session, task_id, TaskStatus.QUEUED)
        append_task_event(
            self.session,
            task_run_id=task_id,
            event_type="resumed",
            message="Task resumed to queued",
        )

    def cancel_task(self, task_id: str) -> None:
        from ..storage.repositories import update_task_status, append_task_event

        update_task_status(self.session, task_id, TaskStatus.CANCELLED)
        append_task_event(
            self.session,
            task_run_id=task_id,
            event_type="cancelled",
            message="Task cancelled",
        )
