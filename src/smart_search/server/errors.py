"""Error handlers for the cloud server."""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

_logger = logging.getLogger(__name__)


def register_error_handlers(app: FastAPI) -> None:
    """Register global error handlers on the FastAPI app."""

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        request_id = getattr(getattr(request, "state", None), "tool_context", None)
        request_id_value = getattr(request_id, "request_id", "")
        _logger.exception("Unhandled server error request_id=%s type=%s", request_id_value, type(exc).__name__)
        return JSONResponse(
            status_code=500,
            content={"ok": False, "error_type": "runtime_error", "error": "Internal server error", "request_id": request_id_value},
        )
