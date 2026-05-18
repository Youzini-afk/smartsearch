"""Task worker – processes queued task runs by executing their DAG nodes.

run_once() processes a single task run. run_forever() polls in a loop.
Designed to be run as a standalone process or embedded.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from sqlalchemy.orm import Session

from .states import TaskStatus, NodeStatus

_logger = logging.getLogger(__name__)


class TaskWorker:
    """Processes task runs from the DB-backed queue."""

    def __init__(self, session_factory: Any, worker_id: str = "default") -> None:
        self.session_factory = session_factory
        self.worker_id = worker_id
        self._running = False

    def run_once(self) -> bool:
        """Claim and execute one task run. Returns True if a task was processed."""
        from ..storage.repositories import (
            claim_next_task,
            list_task_nodes,
            update_node_status,
            update_task_status,
            append_task_event,
            create_task_attempt,
            finish_task_attempt,
            get_task_run,
        )
        from .deep import execute_node

        session = self.session_factory()
        try:
            # Claim next task
            tr = claim_next_task(session, worker_id=self.worker_id)
            if tr is None:
                return False

            append_task_event(
                session,
                task_run_id=tr.id,
                event_type="started",
                message=f"Worker {self.worker_id} picked up task",
            )
            session.commit()

            # Process all ready nodes until completion or blockage
            max_iterations = 50  # safety guard
            for _ in range(max_iterations):
                # Check if task is paused/cancelled
                session.expire(tr)
                if tr.status in (TaskStatus.PAUSED, TaskStatus.CANCELLED):
                    _logger.info("Task %s is %s, stopping", tr.id, tr.status)
                    return True

                nodes = list(list_task_nodes(session, tr.id))
                ready_nodes = self._find_ready_nodes(nodes)

                if not ready_nodes:
                    # Check if all done
                    all_done = all(
                        n.status in NodeStatus.TERMINAL
                        for n in nodes
                    )
                    if all_done:
                        # Check for failures
                        any_failed = any(n.status == NodeStatus.FAILED for n in nodes)
                        if any_failed:
                            update_task_status(session, tr.id, TaskStatus.FAILED, error="One or more nodes failed")
                            append_task_event(session, task_run_id=tr.id, event_type="failed", message="Task failed: node failure(s)")
                        else:
                            update_task_status(session, tr.id, TaskStatus.COMPLETED, result={"nodes_completed": len(nodes)})
                            append_task_event(session, task_run_id=tr.id, event_type="completed", message="All nodes completed")
                        session.commit()
                        return True
                    # Blocked – no ready nodes and not all done
                    _logger.info("Task %s blocked – no ready nodes", tr.id)
                    return True

                # Execute first ready node
                node = ready_nodes[0]
                update_node_status(session, node.id, NodeStatus.RUNNING)
                attempt = create_task_attempt(session, node_id=node.id, attempt_number=node.attempt_count + 1)
                append_task_event(
                    session,
                    task_run_id=tr.id,
                    node_id=node.id,
                    event_type="node_started",
                    message=f"Node {node.name} started",
                )
                session.commit()

                try:
                    result = execute_node(node, ctx={"task_run_id": tr.id, "worker_id": self.worker_id})
                    update_node_status(session, node.id, NodeStatus.COMPLETED, result=result)
                    finish_task_attempt(session, attempt.id, "completed", result=result)
                    append_task_event(
                        session,
                        task_run_id=tr.id,
                        node_id=node.id,
                        event_type="node_completed",
                        message=f"Node {node.name} completed",
                        detail=result,
                    )
                except Exception as exc:
                    _logger.exception("Node %s failed: %s", node.id, exc)
                    update_node_status(session, node.id, NodeStatus.FAILED, error=str(exc))
                    finish_task_attempt(session, attempt.id, "failed", error=str(exc))
                    append_task_event(
                        session,
                        task_run_id=tr.id,
                        node_id=node.id,
                        event_type="node_failed",
                        message=f"Node {node.name} failed: {exc}",
                    )

                session.commit()

            return True

        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def run_forever(self, poll_interval: float = 2.0) -> None:
        """Poll for tasks and process them in a loop."""
        self._running = True
        _logger.info("Worker %s starting, poll_interval=%.1fs", self.worker_id, poll_interval)
        while self._running:
            try:
                processed = self.run_once()
                if not processed:
                    time.sleep(poll_interval)
            except KeyboardInterrupt:
                _logger.info("Worker interrupted")
                self._running = False
                break
            except Exception:
                _logger.exception("Worker error, retrying in %.1fs", poll_interval)
                time.sleep(poll_interval)

    def stop(self) -> None:
        self._running = False

    @staticmethod
    def _find_ready_nodes(nodes: list[Any]) -> list[Any]:
        """Find nodes whose dependencies are all completed."""
        completed_ids: set[str] = set()
        for n in nodes:
            if n.status == NodeStatus.COMPLETED:
                completed_ids.add(n.id)
        ready = []
        for n in nodes:
            if n.status != NodeStatus.PENDING:
                continue
            deps = n.depends_on or []
            if all(d in completed_ids for d in deps):
                ready.append(n)
        return ready


def main() -> None:
    """CLI entry point for the worker process."""
    import os
    import sys

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )

    from ..storage.db import create_engine_from_url, create_session_factory

    db_url = os.getenv("SMART_SEARCH_DATABASE_URL", "sqlite:///smart-search-cloud.db")
    engine = create_engine_from_url(db_url)
    session_factory = create_session_factory(engine)

    poll_interval = float(os.getenv("SMART_SEARCH_WORKER_POLL_INTERVAL", "2.0"))
    worker_id = os.getenv("SMART_SEARCH_WORKER_ID", "default")

    worker = TaskWorker(session_factory, worker_id=worker_id)
    _logger.info("Starting worker with db_url=%s worker_id=%s", db_url[:30], worker_id)

    try:
        worker.run_forever(poll_interval=poll_interval)
    except KeyboardInterrupt:
        worker.stop()
        sys.exit(0)
