"""FastAPI dependencies – Bearer auth, DB session, ToolContext factory."""

from __future__ import annotations

import uuid
from typing import Annotated, Any

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from ..auth.permissions import ScopeSet
from ..auth.tokens import verify_token
from ..runtime.context import ToolContext

_bearer_scheme = HTTPBearer(auto_error=False)


class AuthError(HTTPException):
    """Raised when authentication fails (401)."""

    def __init__(self, detail: str = "Unauthorized") -> None:
        super().__init__(status_code=status.HTTP_401_UNAUTHORIZED, detail=detail)


class ForbiddenError(HTTPException):
    """Raised when the token lacks required scope (403)."""

    def __init__(self, detail: str = "Forbidden") -> None:
        super().__init__(status_code=status.HTTP_403_FORBIDDEN, detail=detail)


def _get_session_factory(request: Request) -> Any:
    """Retrieve the session_factory from app state."""
    sf = getattr(request.app.state, "session_factory", None)
    if sf is None:
        raise RuntimeError("session_factory not configured on app.state")
    return sf


async def require_bearer(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer_scheme)],
) -> ToolContext:
    """Validate Bearer token and return a ToolContext.

    Opens a DB session and stores it on ``request.state.db_session``
    for use by the route handler and the cleanup middleware.

    Returns 401 if token is missing / invalid.
    Scope checks are handled by route-specific ``require_scope`` dependencies.
    """
    if credentials is None:
        raise AuthError("Missing Authorization header")

    token_str = credentials.credentials
    session_factory = _get_session_factory(request)

    # Open a session that lives for the entire request
    session = session_factory()
    request.state.db_session = session

    try:
        api_token = verify_token(session, token_str)
    except Exception:
        session.close()
        request.state.db_session = None
        raise AuthError("Token verification failed")

    if api_token is None:
        session.close()
        request.state.db_session = None
        raise AuthError("Invalid or expired token")

    scope_set = ScopeSet.from_dict(api_token.scopes)

    ctx = ToolContext(
        request_id=str(uuid.uuid4()),
        tenant_id=api_token.tenant_id,
        user_id=api_token.user_id,
        token_id=api_token.id,
        scopes=list(scope_set.permissions),
    )

    # Store context on request state for downstream use
    request.state.tool_context = ctx
    request.state.api_token = api_token

    return ctx


def require_scope(permission: str):
    """Create a dependency that checks a specific permission on the ToolContext."""

    async def _check(
        request: Request,
        ctx: Annotated[ToolContext, Depends(require_bearer)],
    ) -> ToolContext:

        scope_set = ScopeSet(permissions=frozenset(ctx.scopes))
        if not scope_set.allows(permission):
            raise ForbiddenError(f"Token lacks {permission} scope")
        return ctx

    return _check
