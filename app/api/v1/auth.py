from typing import Literal

from fastapi import APIRouter, Depends
from motor.motor_asyncio import AsyncIOMotorDatabase
from pydantic import BaseModel, Field
from starlette import status

from app.core.database import get_database
from app.core.exceptions import AppHTTPException
from app.schemas.base_envelope import ApiResponse, success_response
from app.services.auth_service import INVALID_CREDENTIALS, login_user

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1)
    password: str = Field(..., min_length=1)


class AuthUser(BaseModel):
    username: str
    role: Literal["manager", "staff"]
    staff_id: str | None = None


class LoginResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"]
    user: AuthUser


@router.post(
    "/login",
    response_model=ApiResponse[LoginResponse],
    summary="Dang nhap va nhan JWT",
)
async def login(
    body: LoginRequest,
    db: AsyncIOMotorDatabase = Depends(get_database),
) -> ApiResponse[LoginResponse]:
    try:
        data = await login_user(db, username=body.username, password=body.password)
    except ValueError as exc:
        if str(exc) == INVALID_CREDENTIALS:
            raise AppHTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Tài khoản hoặc mật khẩu không chính xác",
                error_code=INVALID_CREDENTIALS,
            ) from exc
        raise

    return success_response(
        data=LoginResponse.model_validate(data),
        message="Đăng nhập thành công",
    )
