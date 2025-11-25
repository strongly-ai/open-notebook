"""
Authentication middleware for Open Notebook.

Supports two authentication modes:
1. Strongly.AI header-based auth (X-Auth-* headers from platform proxy)
2. Password-based auth (OPEN_NOTEBOOK_PASSWORD environment variable)

When running on Strongly.AI platform, header-based auth takes precedence.
"""

import os
from typing import Optional

from fastapi import HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from loguru import logger
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from api.strongly import StronglyUser, get_user_from_headers


class StronglyAuthMiddleware(BaseHTTPMiddleware):
    """
    Middleware for Strongly.AI platform authentication.

    Authenticates users via X-Auth-* headers injected by the Strongly.AI proxy.
    When headers are present, user info is attached to request.state.
    Falls back to password auth if headers are not present.
    """

    def __init__(self, app, excluded_paths: Optional[list] = None):
        super().__init__(app)
        self.excluded_paths = excluded_paths or [
            "/", "/health", "/docs", "/openapi.json", "/redoc"
        ]
        self.strongly_mode = os.environ.get("STRONGLY_MODE", "false").lower() == "true"
        self.password = os.environ.get("OPEN_NOTEBOOK_PASSWORD")

    async def dispatch(self, request: Request, call_next):
        # Skip authentication for excluded paths
        if request.url.path in self.excluded_paths:
            return await call_next(request)

        # Skip authentication for CORS preflight requests (OPTIONS)
        if request.method == "OPTIONS":
            return await call_next(request)

        # Try Strongly.AI header-based auth first
        headers = {k.lower(): v for k, v in request.headers.items()}
        user = get_user_from_headers(headers)

        if user:
            # User authenticated via Strongly headers
            if not user.authenticated:
                return JSONResponse(
                    status_code=401,
                    content={"detail": "User not authenticated"},
                )

            # Attach user to request state for downstream use
            request.state.strongly_user = user
            logger.debug(f"Authenticated via Strongly: {user.email}")
            return await call_next(request)

        # In Strongly mode, require headers (no fallback)
        if self.strongly_mode:
            return JSONResponse(
                status_code=401,
                content={"detail": "Missing Strongly.AI authentication headers"},
            )

        # Fall back to password authentication
        if self.password:
            auth_header = request.headers.get("Authorization")

            if not auth_header:
                return JSONResponse(
                    status_code=401,
                    content={"detail": "Missing authorization header"},
                    headers={"WWW-Authenticate": "Bearer"}
                )

            try:
                scheme, credentials = auth_header.split(" ", 1)
                if scheme.lower() != "bearer":
                    raise ValueError("Invalid authentication scheme")
            except ValueError:
                return JSONResponse(
                    status_code=401,
                    content={"detail": "Invalid authorization header format"},
                    headers={"WWW-Authenticate": "Bearer"}
                )

            if credentials != self.password:
                return JSONResponse(
                    status_code=401,
                    content={"detail": "Invalid password"},
                    headers={"WWW-Authenticate": "Bearer"}
                )

        # No auth required or password auth passed
        return await call_next(request)


# Legacy middleware for backward compatibility
class PasswordAuthMiddleware(BaseHTTPMiddleware):
    """
    Middleware to check password authentication for all API requests.
    Only active when OPEN_NOTEBOOK_PASSWORD environment variable is set.

    Note: Consider using StronglyAuthMiddleware instead, which supports both
    header-based and password-based authentication.
    """

    def __init__(self, app, excluded_paths: Optional[list] = None):
        super().__init__(app)
        self.password = os.environ.get("OPEN_NOTEBOOK_PASSWORD")
        self.excluded_paths = excluded_paths or ["/", "/health", "/docs", "/openapi.json", "/redoc"]

    async def dispatch(self, request: Request, call_next):
        # Skip authentication if no password is set
        if not self.password:
            return await call_next(request)

        # Skip authentication for excluded paths
        if request.url.path in self.excluded_paths:
            return await call_next(request)

        # Skip authentication for CORS preflight requests (OPTIONS)
        if request.method == "OPTIONS":
            return await call_next(request)

        # Check authorization header
        auth_header = request.headers.get("Authorization")

        if not auth_header:
            return JSONResponse(
                status_code=401,
                content={"detail": "Missing authorization header"},
                headers={"WWW-Authenticate": "Bearer"}
            )

        # Expected format: "Bearer {password}"
        try:
            scheme, credentials = auth_header.split(" ", 1)
            if scheme.lower() != "bearer":
                raise ValueError("Invalid authentication scheme")
        except ValueError:
            return JSONResponse(
                status_code=401,
                content={"detail": "Invalid authorization header format"},
                headers={"WWW-Authenticate": "Bearer"}
            )

        # Check password
        if credentials != self.password:
            return JSONResponse(
                status_code=401,
                content={"detail": "Invalid password"},
                headers={"WWW-Authenticate": "Bearer"}
            )

        # Password is correct, proceed with the request
        response = await call_next(request)
        return response


# Optional: HTTPBearer security scheme for OpenAPI documentation
security = HTTPBearer(auto_error=False)


def get_current_user(request: Request) -> Optional[StronglyUser]:
    """
    Get the current authenticated user from request state.

    Returns StronglyUser if authenticated via Strongly headers, None otherwise.
    """
    return getattr(request.state, "strongly_user", None)


def check_api_password(credentials: Optional[HTTPAuthorizationCredentials] = None) -> bool:
    """
    Utility function to check API password.
    Can be used as a dependency in individual routes if needed.
    """
    password = os.environ.get("OPEN_NOTEBOOK_PASSWORD")

    # No password set, allow access
    if not password:
        return True

    # No credentials provided
    if not credentials:
        raise HTTPException(
            status_code=401,
            detail="Missing authorization",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Check password
    if credentials.credentials != password:
        raise HTTPException(
            status_code=401,
            detail="Invalid password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return True
