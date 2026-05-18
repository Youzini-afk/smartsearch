"""FastAPI app factory – create_app(engine, session_factory).

The app provides:
- ``GET /health`` – liveness check (no auth required).
- ``POST /api/tools/*`` – tool endpoints (Bearer auth required).
- ``/mcp`` – optional MCP server mount (if mcp package installed).
"""

from __future__ import annotations

from contextlib import asynccontextmanager
import logging
import os
from typing import Any

from fastapi import Depends, FastAPI, Request

from ..storage.db import create_engine_from_url, create_session_factory, init_db
from .dependencies import require_scope
from .errors import register_error_handlers
from .schemas import (
    DeepPlanRequest,
    DoctorRequest,
    DocsSearchRequest,
    FetchUrlRequest,
    MapSiteRequest,
    SearchRequest,
    WebSearchRequest,
)
from .tools import (
    dispatch_deep_plan,
    dispatch_doctor,
    dispatch_docs_search,
    dispatch_fetch_url,
    dispatch_map_site,
    dispatch_search,
    dispatch_web_search,
)
from ..runtime.context import ToolContext

_logger = logging.getLogger(__name__)


def create_app(
    engine: Any = None,
    session_factory: Any = None,
) -> FastAPI:
    """Create and return the FastAPI application.

    Parameters
    ----------
    engine : sqlalchemy.Engine, optional
        If provided, used directly. Otherwise created from env vars.
    session_factory : sqlalchemy.orm.sessionmaker, optional
        If provided, used directly. Otherwise created from *engine*.

    The app runs ``init_db`` on startup to ensure tables exist.
    """

    # ---- Resolve engine / session_factory ---------------------------------
    if engine is None:
        engine = create_engine_from_url()
    if session_factory is None:
        session_factory = create_session_factory(engine)

    # Capture in closure for lifespan
    _engine = engine
    _session_factory = session_factory

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # Startup
        init_db(_engine)
        app.state.engine = _engine
        app.state.session_factory = _session_factory
        yield
        # Shutdown: nothing to clean up

    app = FastAPI(
        title="Smart Search Cloud API",
        version="0.1.0",
        docs_url="/docs",
        redoc_url=None,
        lifespan=lifespan,
    )

    # Set state immediately so TestClient works without lifespan
    app.state.engine = _engine
    app.state.session_factory = _session_factory

    # ---- Middleware to close DB sessions after each request -----------------

    @app.middleware("http")
    async def _db_session_lifecycle(request: Request, call_next):
        try:
            response = await call_next(request)
            sess = getattr(request.state, "db_session", None)
            if sess is not None:
                sess.commit()
            return response
        except Exception:
            sess = getattr(request.state, "db_session", None)
            if sess is not None:
                try:
                    sess.rollback()
                except Exception:
                    pass
            raise
        finally:
            sess = getattr(request.state, "db_session", None)
            if sess is not None:
                try:
                    sess.close()
                except Exception:
                    pass
                request.state.db_session = None

    # ---- Health endpoint (no auth) -----------------------------------------

    @app.get("/health", tags=["system"])
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    # ---- Error handlers ----------------------------------------------------

    register_error_handlers(app)

    # ---- Tool routes --------------------------------------------------------

    @app.post("/api/tools/search", tags=["tools"])
    async def api_search(
        body: SearchRequest,
        request: Request,
        ctx: ToolContext = Depends(require_scope("search:read")),
    ) -> dict[str, Any]:
        session = request.state.db_session
        return await dispatch_search(
            ctx, session,
            query=body.query,
            platform=body.platform,
            model=body.model,
            extra_sources=body.extra_sources,
            validation=body.validation,
            fallback=body.fallback,
            providers=body.providers,
        )

    @app.post("/api/tools/fetch_url", tags=["tools"])
    async def api_fetch_url(
        body: FetchUrlRequest,
        request: Request,
        ctx: ToolContext = Depends(require_scope("fetch:read")),
    ) -> dict[str, Any]:
        session = request.state.db_session
        return await dispatch_fetch_url(ctx, session, url=body.url)

    @app.post("/api/tools/map_site", tags=["tools"])
    async def api_map_site(
        body: MapSiteRequest,
        request: Request,
        ctx: ToolContext = Depends(require_scope("fetch:read")),
    ) -> dict[str, Any]:
        session = request.state.db_session
        return await dispatch_map_site(
            ctx, session,
            url=body.url,
            instructions=body.instructions,
            max_depth=body.max_depth,
            max_breadth=body.max_breadth,
            limit=body.limit,
            timeout=body.timeout,
        )

    @app.post("/api/tools/docs_search", tags=["tools"])
    async def api_docs_search(
        body: DocsSearchRequest,
        request: Request,
        ctx: ToolContext = Depends(require_scope("search:read")),
    ) -> dict[str, Any]:
        session = request.state.db_session
        return await dispatch_docs_search(
            ctx, session,
            query=body.query,
            library_id=body.library_id,
            name=body.name,
        )

    @app.post("/api/tools/web_search", tags=["tools"])
    async def api_web_search(
        body: WebSearchRequest,
        request: Request,
        ctx: ToolContext = Depends(require_scope("search:read")),
    ) -> dict[str, Any]:
        session = request.state.db_session
        return await dispatch_web_search(
            ctx, session,
            query=body.query,
            count=body.count,
            provider=body.provider,
        )

    @app.post("/api/tools/deep_plan", tags=["tools"])
    async def api_deep_plan(
        body: DeepPlanRequest,
        request: Request,
        ctx: ToolContext = Depends(require_scope("deep:read")),
    ) -> dict[str, Any]:
        session = request.state.db_session
        return dispatch_deep_plan(
            ctx, session,
            query=body.query,
            budget=body.budget,
            evidence_dir=body.evidence_dir,
        )

    @app.post("/api/tools/doctor", tags=["tools"])
    async def api_doctor(
        request: Request,
        ctx: ToolContext = Depends(require_scope("doctor:read")),
    ) -> dict[str, Any]:
        session = request.state.db_session
        return await dispatch_doctor(ctx, session)

    # ---- Admin WebUI + API -----------------------------------------------

    try:
        from ..admin import create_admin_router
        admin_router = create_admin_router()
        app.include_router(admin_router)
    except Exception as exc:
        _logger.warning("Admin router could not be mounted: %s", type(exc).__name__)

    # ---- Task API ---------------------------------------------------------

    try:
        from .task_routes import create_task_router
        task_router = create_task_router()
        app.include_router(task_router)
    except Exception as exc:
        _logger.warning("Task router could not be mounted: %s", type(exc).__name__)

    # ---- MCP mount (optional) ----------------------------------------------

    if os.getenv("SMART_SEARCH_ENABLE_MCP", "false").lower() == "true":
        _try_mount_mcp(app, session_factory)
    else:
        app.state.mcp_mounted = False

    return app


def _try_mount_mcp(app: FastAPI, session_factory: Any) -> None:
    """Attempt to mount the MCP server at /mcp.

    If the ``mcp`` package is not installed, this is a no-op – the
    rest of the app continues to work normally.
    """
    try:
        from .mcp_server import create_mcp_server

        mcp_app = create_mcp_server(session_factory)
        if mcp_app is not None:
            app.mount("/mcp", mcp_app)
            app.state.mcp_mounted = True
        else:
            app.state.mcp_mounted = False
    except ImportError:
        app.state.mcp_mounted = False
        _logger.info("MCP SDK is not installed; /mcp mount disabled")
    except Exception as exc:
        app.state.mcp_mounted = False
        _logger.warning("MCP server creation failed; /mcp mount disabled: %s", type(exc).__name__)
