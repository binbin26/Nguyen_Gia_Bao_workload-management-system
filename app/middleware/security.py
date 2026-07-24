"""CSRF enforcement and browser security headers."""

from __future__ import annotations

import secrets
from collections.abc import Awaitable, Callable

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from app.core.config import settings
from app.core.security import (
    CSRF_COOKIE_NAME,
    CSRF_HEADER_NAME,
    csrf_binding_from_cookies,
    validate_csrf_token,
)

UNSAFE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})

# This route is authenticated with a server-to-server secret, never browser
# cookies. Applying browser CSRF checks would only break the cron integration.
CSRF_EXEMPT_PATHS = frozenset({"/api/v1/system/daily-reset"})

CSP_POLICY = "; ".join(
    (
        "default-src 'self'",
        # No unsafe-inline/unsafe-eval: injected inline JavaScript cannot run.
        "script-src 'self'",
        # Existing React components use a small number of style attributes.
        # unsafe-inline applies only to CSS here; it does not relax script-src.
        "style-src 'self' 'unsafe-inline'",
        "img-src 'self' data:",
        "font-src 'self'",
        "connect-src 'self'",
        "object-src 'none'",
        "base-uri 'none'",
        "frame-ancestors 'none'",
        "form-action 'self'",
    )
)


class SecurityMiddleware(BaseHTTPMiddleware):
    """Reject forged mutations and attach defense-in-depth response headers."""

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        response: Response
        if self._requires_csrf(request):
            error = self._validate_request(request)
            if error is not None:
                response = error
            else:
                response = await call_next(request)
        else:
            response = await call_next(request)

        self._set_security_headers(response)
        return response

    @staticmethod
    def _requires_csrf(request: Request) -> bool:
        return (
            request.method.upper() in UNSAFE_METHODS
            and request.url.path not in CSRF_EXEMPT_PATHS
        )

    @staticmethod
    def _validate_request(request: Request) -> JSONResponse | None:
        origin = request.headers.get("origin")
        if origin and origin.rstrip("/") not in {
            item.rstrip("/") for item in settings.CORS_ALLOWED_ORIGINS
        }:
            return SecurityMiddleware._csrf_error(
                "Nguồn gửi yêu cầu không được phép.",
                "CSRF_ORIGIN_MISMATCH",
            )

        cookie_token = request.cookies.get(CSRF_COOKIE_NAME)
        header_token = request.headers.get(CSRF_HEADER_NAME)
        if not cookie_token or not header_token:
            return SecurityMiddleware._csrf_error(
                "Thiếu CSRF token.",
                "CSRF_TOKEN_MISSING",
            )
        if not secrets.compare_digest(cookie_token, header_token):
            return SecurityMiddleware._csrf_error(
                "CSRF token không khớp.",
                "CSRF_TOKEN_MISMATCH",
            )

        session_binding = csrf_binding_from_cookies(dict(request.cookies))
        if not validate_csrf_token(cookie_token, session_binding):
            return SecurityMiddleware._csrf_error(
                "CSRF token không hợp lệ hoặc không thuộc phiên hiện tại.",
                "CSRF_TOKEN_INVALID",
            )
        return None

    @staticmethod
    def _csrf_error(message: str, error_code: str) -> JSONResponse:
        return JSONResponse(
            status_code=403,
            content={
                "success": False,
                "data": None,
                "message": message,
                "error_code": error_code,
            },
        )

    @staticmethod
    def _set_security_headers(response: Response) -> None:
        response.headers["Content-Security-Policy"] = CSP_POLICY
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = (
            "camera=(), microphone=(), geolocation=(), payment=()"
        )
        if settings.COOKIE_SECURE:
            response.headers["Strict-Transport-Security"] = (
                "max-age=31536000; includeSubDomains"
            )
