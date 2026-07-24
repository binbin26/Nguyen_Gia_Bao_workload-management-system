from typing import Literal

from fastapi import APIRouter, Depends, Request, Response
from motor.motor_asyncio import AsyncIOMotorDatabase
from pydantic import BaseModel, Field
from starlette import status

from app.api.dependencies import get_current_user
from app.core.database import get_database
from app.core.exceptions import AppHTTPException
from app.core.security import (
    REFRESH_COOKIE_NAME,
    clear_auth_cookies,
    create_csrf_token,
    csrf_binding_from_cookies,
    set_auth_cookies,
    set_csrf_cookie,
)
from app.schemas.base_envelope import ApiResponse, success_response
from app.services.auth_service import (
    INVALID_CREDENTIALS,
    INVALID_REFRESH_SESSION,
    login_user,
    revoke_refresh_session,
    rotate_refresh_session,
)

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1)
    password: str = Field(..., min_length=1)


class AuthUser(BaseModel):
    username: str
    role: Literal["manager", "staff"]
    staff_id: str | None = None


class LoginResponse(BaseModel):
    user: AuthUser


class CsrfResponse(BaseModel):
    csrf_token: str


@router.post(
    "/login",
    response_model=ApiResponse[LoginResponse],
    summary="Đăng nhập và nhận access/refresh token qua HttpOnly cookie",
)
async def login(
    body: LoginRequest,
    request: Request,
    response: Response,
    db: AsyncIOMotorDatabase = Depends(get_database),
) -> ApiResponse[LoginResponse]:
    try:
        user, tokens = await login_user(
            db,
            username=body.username,
            password=body.password,
        )
    except ValueError as exc:
        if str(exc) == INVALID_CREDENTIALS:
            raise AppHTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Tài khoản hoặc mật khẩu không chính xác",
                error_code=INVALID_CREDENTIALS,
            ) from exc
        raise

    # A successful account switch invalidates the refresh session that was
    # previously attached to this browser before overwriting its cookie.
    await revoke_refresh_session(db, request.cookies.get(REFRESH_COOKIE_NAME))
    # Neither JWT is returned in JSON, so injected JavaScript cannot exfiltrate
    # it. FastAPI copies these Set-Cookie headers to the final model response.
    set_auth_cookies(response, tokens)
    csrf_token = create_csrf_token(tokens.session_id)
    set_csrf_cookie(response, csrf_token)
    return success_response(
        data=LoginResponse(user=AuthUser.model_validate(user)),
        message="Đăng nhập thành công",
    )


@router.get(
    "/csrf",
    response_model=ApiResponse[CsrfResponse],
    summary="Cấp CSRF token cho SPA",
)
async def issue_csrf_token(request: Request, response: Response) -> ApiResponse[CsrfResponse]:
    """Issue a signed token; this safe GET never changes application data."""
    binding = csrf_binding_from_cookies(dict(request.cookies))
    token = create_csrf_token(binding)
    set_csrf_cookie(response, token)
    return success_response(data=CsrfResponse(csrf_token=token))


@router.post(
    "/refresh",
    response_model=ApiResponse[LoginResponse],
    summary="Xoay vòng refresh token và cấp access token mới",
)
async def refresh_session(
    request: Request,
    response: Response,
    db: AsyncIOMotorDatabase = Depends(get_database),
) -> ApiResponse[LoginResponse]:
    refresh_token = request.cookies.get(REFRESH_COOKIE_NAME)
    if not refresh_token:
        raise AppHTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Không có refresh token",
            error_code=INVALID_REFRESH_SESSION,
        )

    try:
        user, tokens = await rotate_refresh_session(db, refresh_token)
    except ValueError as exc:
        if str(exc) == INVALID_REFRESH_SESSION:
            raise AppHTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Refresh token không hợp lệ, đã hết hạn hoặc đã được sử dụng",
                error_code=INVALID_REFRESH_SESSION,
            ) from exc
        raise

    set_auth_cookies(response, tokens)
    return success_response(
        data=LoginResponse(user=AuthUser.model_validate(user)),
        message="Làm mới phiên đăng nhập thành công",
    )


@router.get(
    "/me",
    response_model=ApiResponse[LoginResponse],
    summary="Lấy người dùng của phiên cookie hiện tại",
)
async def get_session_user(
    user: dict = Depends(get_current_user),
) -> ApiResponse[LoginResponse]:
    return success_response(
        data=LoginResponse(
            user=AuthUser(
                username=user["sub"],
                role=user["role"],
                staff_id=user.get("staff_id"),
            )
        )
    )


@router.post(
    "/logout",
    response_model=ApiResponse[None],
    summary="Thu hồi refresh session và xóa cookie xác thực",
)
async def logout(
    request: Request,
    response: Response,
    db: AsyncIOMotorDatabase = Depends(get_database),
) -> ApiResponse[None]:
    await revoke_refresh_session(db, request.cookies.get(REFRESH_COOKIE_NAME))
    clear_auth_cookies(response)
    return success_response(data=None, message="Đăng xuất thành công")
