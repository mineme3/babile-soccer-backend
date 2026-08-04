"""Security middleware for the Babile Sport API.

Provides:
- Dashboard-only access restriction for admin endpoints
- Security headers (X-Content-Type-Options, X-Frame-Options, etc.)
- Rate limiting for auth endpoints (login, register, forgot-password)
"""

from __future__ import annotations

import logging
import time
from collections import defaultdict

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse

logger = logging.getLogger(__name__)

DASHBOARD_HEADER = "X-Dashboard-Client"
DASHBOARD_HEADER_VALUE = "babile-dashboard"


class DashboardOnlyMiddleware(BaseHTTPMiddleware):
    """Block admin endpoints unless the request carries the dashboard header."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint):
        path = request.url.path

        # Only protect admin-specific routes
        if path.startswith("/api/v1/admin"):
            client_header = request.headers.get(DASHBOARD_HEADER)
            if client_header != DASHBOARD_HEADER_VALUE:
                logger.warning(
                    "Blocked non-dashboard access to admin endpoint: %s from %s",
                    path,
                    request.client.host if request.client else "unknown",
                )
                return JSONResponse(
                    status_code=403,
                    content={
                        "error": {
                            "code": "FORBIDDEN",
                            "message": "This endpoint is only accessible from the admin dashboard.",
                            "clue": "Use the web dashboard at /login to access admin features.",
                        }
                    },
                )

        return await call_next(request)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add security headers to all responses."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        if not request.url.path.startswith("/docs") and not request.url.path.startswith("/redoc"):
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        return response


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Simple in-memory rate limiter for sensitive endpoints.

    Limits:
    - Login: 10 attempts per minute per IP
    - Register: 5 attempts per minute per IP
    - Forgot password: 3 attempts per minute per IP
    """

    RATE_LIMITS: dict[str, tuple[int, int]] = {
        "/api/v1/auth/login": (10, 60),
        "/api/v1/auth/register": (5, 60),
        "/api/v1/auth/forgot-password": (3, 60),
        "/api/v1/auth/google": (5, 60),
    }

    def __init__(self, app):
        super().__init__(app)
        self._requests: dict[str, list[float]] = defaultdict(list)

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint):
        path = request.url.path
        if path not in self.RATE_LIMITS:
            return await call_next(request)

        max_requests, window = self.RATE_LIMITS[path]
        client_ip = request.client.host if request.client else "unknown"
        key = f"{path}:{client_ip}"
        now = time.time()

        # Clean old entries
        self._requests[key] = [t for t in self._requests[key] if now - t < window]

        if len(self._requests[key]) >= max_requests:
            logger.warning("Rate limit exceeded for %s from %s", path, client_ip)
            return JSONResponse(
                status_code=429,
                content={
                    "error": {
                        "code": "RATE_LIMITED",
                        "message": "Too many requests. Please slow down.",
                        "clue": f"You can try again in {window} seconds. This limit protects your account from brute-force attacks.",
                    }
                },
            )

        self._requests[key].append(now)
        return await call_next(request)
