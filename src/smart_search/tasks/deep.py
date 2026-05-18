"""Deep Research DAG builder and node executor.

build_deep_research_dag creates the plan/search/fetch/synthesize/finalize
nodes. execute_node runs a single node using service functions or
monkeypatch-able hooks (for testing without network).
"""

from __future__ import annotations

import logging
from typing import Any

from .states import NodeStatus

_logger = logging.getLogger(__name__)


# Registry of node executors; can be monkeypatched in tests.
_NODE_EXECUTORS: dict[str, Any] = {}


def register_node_executor(node_type: str, fn: Any) -> None:
    """Register a callable for a node type. Used for monkeypatching in tests."""
    _NODE_EXECUTORS[node_type] = fn


def build_deep_research_dag(
    topic: str,
    depth: str = "standard",
    max_sources: int = 5,
) -> list[dict[str, Any]]:
    """Build a deep research DAG as a list of node descriptors.

    Each node has: key, node_type, name, depends_on (list of keys), config, status.
    """
    nodes: list[dict[str, Any]] = []

    nodes.append({
        "key": "plan",
        "node_type": "plan",
        "name": "Plan research sub-questions",
        "depends_on": [],
        "config": {"topic": topic, "depth": depth, "max_sources": max_sources},
        "status": NodeStatus.PENDING,
    })

    nodes.append({
        "key": "search",
        "node_type": "search",
        "name": "Search for sources",
        "depends_on": ["plan"],
        "config": {"max_sources": max_sources},
        "status": NodeStatus.PENDING,
    })

    nodes.append({
        "key": "fetch",
        "node_type": "fetch",
        "name": "Fetch key URLs",
        "depends_on": ["search"],
        "config": {},
        "status": NodeStatus.PENDING,
    })

    nodes.append({
        "key": "synthesize",
        "node_type": "synthesize",
        "name": "Synthesize findings",
        "depends_on": ["fetch"],
        "config": {},
        "status": NodeStatus.PENDING,
    })

    nodes.append({
        "key": "finalize",
        "node_type": "finalize",
        "name": "Finalize report",
        "depends_on": ["synthesize"],
        "config": {},
        "status": NodeStatus.PENDING,
    })

    return nodes


def execute_node(node: Any, ctx: dict[str, Any] | None = None) -> dict[str, Any]:
    """Execute a single task node (synchronous).

    Checks _NODE_EXECUTORS first (for monkeypatching), then falls back
    to a default implementation. Never makes network calls in default
    impl – returns stub results.

    For async executors, wrap them with ``asyncio.run`` in the caller
    or register a sync wrapper.
    """
    node_type = node.node_type if hasattr(node, "node_type") else node.get("node_type", "unknown")
    _logger.info("Executing node type=%s id=%s", node_type, getattr(node, "id", "?"))

    # Check monkeypatched executor
    executor = _NODE_EXECUTORS.get(node_type)
    if executor is not None:
        if callable(executor):
            result = executor(node, ctx)
            if result is not None:
                return result if isinstance(result, dict) else {"ok": True, "data": result}
        return {"ok": True, "stub": True}

    # Default stub implementation (no network)
    return _default_execute(node_type, node, ctx)


def _default_execute(node_type: str, node: Any, ctx: dict[str, Any] | None) -> dict[str, Any]:
    """Default no-op executor that returns stub results."""
    return {
        "ok": True,
        "node_type": node_type,
        "message": f"Node {node_type} executed (stub)",
        "sources": [],
    }
