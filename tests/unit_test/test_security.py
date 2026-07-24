from fastapi import Request, Response

from app.core.security import (
    ACCESS_COOKIE_NAME,
    CSRF_COOKIE_NAME,
    REFRESH_COOKIE_NAME,
    create_csrf_token,
    create_token_pair,
    set_auth_cookies,
    set_csrf_cookie,
    validate_csrf_token,
)
from app.middleware.security import SecurityMiddleware


def _cookie_headers(response: Response) -> list[str]:
    return [
        value.decode("latin-1")
        for key, value in response.raw_headers
        if key.lower() == b"set-cookie"
    ]


def _request(
    method: str,
    *,
    cookie: str | None = None,
    csrf_header: str | None = None,
) -> Request:
    headers: list[tuple[bytes, bytes]] = []
    if cookie:
        headers.append((b"cookie", cookie.encode("latin-1")))
    if csrf_header:
        headers.append((b"x-csrf-token", csrf_header.encode("latin-1")))
    return Request(
        {
            "type": "http",
            "http_version": "1.1",
            "method": method,
            "scheme": "https",
            "path": "/change",
            "raw_path": b"/change",
            "query_string": b"",
            "headers": headers,
            "client": ("127.0.0.1", 12345),
            "server": ("testserver", 443),
        }
    )


def test_auth_cookies_are_hardened_and_tokens_are_not_in_body():
    user = {"_id": "manager_01", "role": "manager", "staff_id": None}
    tokens = create_token_pair(user)
    response = Response(content=b'{"user":"manager_01"}', media_type="application/json")

    set_auth_cookies(response, tokens)
    cookie_headers = _cookie_headers(response)

    assert len(cookie_headers) == 2
    for cookie in cookie_headers:
        lowered = cookie.lower()
        assert "httponly" in lowered
        assert "secure" in lowered
        assert "samesite=strict" in lowered
        assert "path=/" in lowered
    assert any(cookie.startswith(f"{ACCESS_COOKIE_NAME}=") for cookie in cookie_headers)
    assert any(cookie.startswith(f"{REFRESH_COOKIE_NAME}=") for cookie in cookie_headers)
    assert tokens.access_token.encode() not in response.body
    assert tokens.refresh_token.encode() not in response.body


def test_csrf_token_is_signed_and_bound_to_session():
    token = create_csrf_token("session-a")

    assert validate_csrf_token(token, "session-a") is True
    assert validate_csrf_token(token, "session-b") is False
    assert validate_csrf_token(f"{token[:-1]}0", "session-a") is False


def test_security_middleware_rejects_missing_csrf_and_sets_csp():
    missing = SecurityMiddleware._validate_request(_request("POST"))
    assert missing is not None
    assert missing.status_code == 403
    assert b"CSRF_TOKEN_MISSING" in missing.body

    token = create_csrf_token()
    csrf_cookie_response = Response()
    set_csrf_cookie(csrf_cookie_response, token)
    assert any(
        cookie.startswith(f"{CSRF_COOKIE_NAME}={token}")
        for cookie in _cookie_headers(csrf_cookie_response)
    )

    response = Response()
    SecurityMiddleware._set_security_headers(response)
    policy = response.headers["content-security-policy"]
    assert "script-src 'self'" in policy
    assert "'unsafe-eval'" not in policy

    accepted = SecurityMiddleware._validate_request(
        _request(
            "POST",
            cookie=f"{CSRF_COOKIE_NAME}={token}",
            csrf_header=token,
        )
    )
    assert accepted is None


def test_security_middleware_rejects_mismatched_csrf():
    token = create_csrf_token()
    response = SecurityMiddleware._validate_request(
        _request(
            "POST",
            cookie=f"{CSRF_COOKIE_NAME}={token}",
            csrf_header="wrong",
        )
    )
    assert response is not None
    assert response.status_code == 403
    assert b"CSRF_TOKEN_MISMATCH" in response.body
