from typing import Generic, Optional, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class ApiResponse(BaseModel, Generic[T]):
    """Standard response envelope for all API endpoints."""

    success: bool = True
    data: Optional[T] = None
    message: Optional[str] = None
    error_code: Optional[str] = None


def success_response(
    data: T,
    message: str | None = None,
) -> ApiResponse[T]:
    return ApiResponse(success=True, data=data, message=message, error_code=None)


def error_response(
    message: str,
    error_code: str | None = None,
) -> ApiResponse[None]:
    return ApiResponse(success=False, data=None, message=message, error_code=error_code)
