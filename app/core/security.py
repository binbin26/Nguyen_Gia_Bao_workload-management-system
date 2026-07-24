"""Authentication cookies, JWT creation/validation, and CSRF token helpers."""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

import jwt
from fastapi import Response

from app.core.config import settings

TokenType = Literal["access", "refresh"]
ANONYMOUS_CSRF_BINDING = "anonymous"


def _cookie_name(name: str) -> str:
    """Use browser-enforced prefixes in HTTPS, while allowing explicit HTTP dev."""
    if not settings.COOKIE_SECURE:
        return name
    return f"__Host-{name}"


ACCESS_COOKIE_NAME = _cookie_name("access_token")
REFRESH_COOKIE_NAME = _cookie_name("refresh_token")
CSRF_COOKIE_NAME = _cookie_name("csrf_token")
CSRF_HEADER_NAME = "X-CSRF-Token"


@dataclass(frozen=True)
class TokenPair:
    access_token: str
    refresh_token: str
    refresh_jti: str
    session_id: str
    refresh_expires_at: datetime


def _jwt_secret(token_type: TokenType) -> str:
    return (
        settings.JWT_SECRET_KEY
        if token_type == "access"
        else settings.JWT_REFRESH_SECRET_KEY
    )


def _encode_token(
    user: dict[str, Any],
    *,
    token_type: TokenType,
    expires_delta: timedelta,
    session_id: str,
    token_id: str,
) -> tuple[str, datetime]:
    now = datetime.now(timezone.utc)
    expires_at = now + expires_delta
    payload: dict[str, Any] = {
        "sub": str(user["_id"]),
        "role": user["role"],
        "type": token_type,
        "sid": session_id,
        "jti": token_id,
        "iat": now,
        "nbf": now,
        "exp": expires_at,
        "iss": settings.JWT_ISSUER,
        "aud": settings.JWT_AUDIENCE,
    }
    if user.get("staff_id") is not None:
        payload["staff_id"] = user["staff_id"]

    encoded = jwt.encode(
        payload,
        _jwt_secret(token_type),
        algorithm=settings.JWT_ALGORITHM,
    )
    return encoded, expires_at


def create_token_pair(
    user: dict[str, Any],
    *,
    session_id: str | None = None,
) -> TokenPair:
    """Create a short-lived access JWT and a one-time, rotatable refresh JWT."""
    sid = session_id or secrets.token_urlsafe(32)
    access_token, _ = _encode_token(
        user,
        token_type="access",
        expires_delta=timedelta(minutes=settings.JWT_ACCESS_EXPIRE_MINUTES),
        session_id=sid,
        token_id=secrets.token_urlsafe(24),
    )
    refresh_jti = secrets.token_urlsafe(32)
    refresh_token, refresh_expires_at = _encode_token(
        user,
        token_type="refresh",
        expires_delta=timedelta(days=settings.JWT_REFRESH_EXPIRE_DAYS),
        session_id=sid,
        token_id=refresh_jti,
    )
    return TokenPair(
        access_token=access_token,
        refresh_token=refresh_token,
        refresh_jti=refresh_jti,
        session_id=sid,
        refresh_expires_at=refresh_expires_at,
    )


def decode_token(
    token: str,
    *,
    expected_type: TokenType,
    verify_expiration: bool = True,
) -> dict[str, Any]:
    """Validate signature and registered claims, then enforce the token purpose."""
    payload = jwt.decode(
        token,
        _jwt_secret(expected_type),
        algorithms=[settings.JWT_ALGORITHM],
        audience=settings.JWT_AUDIENCE,
        issuer=settings.JWT_ISSUER,
        options={
            "verify_exp": verify_expiration,
            "require": ["sub", "type", "sid", "jti", "iat", "nbf", "exp"],
        },
    )
    if payload.get("type") != expected_type:
        raise jwt.InvalidTokenError("Incorrect token type")
    return payload


def set_auth_cookies(response: Response, tokens: TokenPair) -> None:
    """Store JWTs where JavaScript cannot read them (mitigates token theft via XSS)."""
    common = {
        "httponly": True,
        # Secure prevents transmission over plaintext HTTP. Only turn it off in
        # an isolated local environment that cannot use HTTPS.
        "secure": settings.COOKIE_SECURE,
        # Strict prevents cookies from accompanying cross-site navigations and
        # requests. The frontend and API must therefore be deployed same-site.
        "samesite": settings.COOKIE_SAMESITE,
        # Omitting Domain makes every cookie host-only.
        "path": "/",
    }
    response.set_cookie(
        key=ACCESS_COOKIE_NAME,
        value=tokens.access_token,
        max_age=settings.JWT_ACCESS_EXPIRE_MINUTES * 60,
        **common,
    )
    response.set_cookie(
        key=REFRESH_COOKIE_NAME,
        value=tokens.refresh_token,
        max_age=settings.JWT_REFRESH_EXPIRE_DAYS * 24 * 60 * 60,
        **common,
    )
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"


def clear_auth_cookies(response: Response) -> None:
    """Delete cookies using the exact attributes/path used when setting them."""
    for name, http_only in (
        (ACCESS_COOKIE_NAME, True),
        (REFRESH_COOKIE_NAME, True),
        (CSRF_COOKIE_NAME, False),
    ):
        response.delete_cookie(
            key=name,
            path="/",
            secure=settings.COOKIE_SECURE,
            httponly=http_only,
            samesite=settings.COOKIE_SAMESITE,
        )
    response.headers["Cache-Control"] = "no-store"


def _b64_encode(value: str) -> str:
    return base64.urlsafe_b64encode(value.encode("utf-8")).rstrip(b"=").decode("ascii")


def _b64_decode(value: str) -> str:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding).decode("utf-8")


def create_csrf_token(session_binding: str = ANONYMOUS_CSRF_BINDING) -> str:
    """Create an HMAC-signed double-submit token bound to the browser session."""
    nonce = secrets.token_urlsafe(32)
    message = f"{session_binding}.{nonce}"
    signature = hmac.new(
        settings.CSRF_SECRET_KEY.encode("utf-8"),
        message.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return f"{_b64_encode(session_binding)}.{nonce}.{signature}"


def validate_csrf_token(token: str, session_binding: str) -> bool:
    try:
        encoded_binding, nonce, supplied_signature = token.split(".", 2)
        token_binding = _b64_decode(encoded_binding)
    except (ValueError, UnicodeError):
        return False

    if not hmac.compare_digest(token_binding, session_binding):
        return False

    message = f"{token_binding}.{nonce}"
    expected_signature = hmac.new(
        settings.CSRF_SECRET_KEY.encode("utf-8"),
        message.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(supplied_signature, expected_signature)


def csrf_binding_from_cookies(cookies: dict[str, str]) -> str:
    """Resolve the signed session id, even when the access token just expired."""
    candidates: tuple[tuple[str, TokenType], ...] = (
        (ACCESS_COOKIE_NAME, "access"),
        (REFRESH_COOKIE_NAME, "refresh"),
    )
    for cookie_name, token_type in candidates:
        token = cookies.get(cookie_name)
        if not token:
            continue
        try:
            payload = decode_token(
                token,
                expected_type=token_type,
                verify_expiration=False,
            )
            session_id = payload.get("sid")
            if isinstance(session_id, str) and session_id:
                return session_id
        except jwt.InvalidTokenError:
            continue
    return ANONYMOUS_CSRF_BINDING


def set_csrf_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=CSRF_COOKIE_NAME,
        value=token,
        # This cookie is intentionally readable so a SPA may use the standard
        # double-submit pattern. It contains no credential or sensitive data.
        httponly=False,
        secure=settings.COOKIE_SECURE,
        samesite=settings.COOKIE_SAMESITE,
        path="/",
        max_age=settings.JWT_REFRESH_EXPIRE_DAYS * 24 * 60 * 60,
    )
    response.headers["Cache-Control"] = "no-store"


def hash_refresh_jti(jti: str) -> str:
    """Avoid storing a directly usable refresh identifier in the database."""
    return hmac.new(
        settings.JWT_REFRESH_SECRET_KEY.encode("utf-8"),
        jti.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
