from typing import Any

import jwt
from fastapi import Depends, HTTPException, Request
from motor.motor_asyncio import AsyncIOMotorDatabase
from starlette import status

from app.core.config import settings
from app.core.database import get_database
from app.core.exceptions import AppHTTPException
from app.core.security import ACCESS_COOKIE_NAME, decode_token
from app.repositories.log_repository import create_pending_overload_log

WORKLOAD_CAP_EXCEEDED = "WORKLOAD_CAP_EXCEEDED"

def evaluate_workload_capacity(
    staff: dict,
    duration_hours: float,
) -> tuple[bool, str | None, dict[str, Any]]:
    """
    Project daily workload and determine whether the new task fits within caps.

    Returns (is_ok, trigger_reason, projection_details).
    """
    caps = staff["workload_caps"]
    projected_tasks = caps["current_daily_tasks"] + 1
    projected_hours = caps["current_daily_hours"] + duration_hours

    tasks_ok = projected_tasks <= caps["max_daily_tasks"]
    hours_ok = projected_hours <= caps["max_daily_hours"]

    details: dict[str, Any] = {
        "staff_id": staff["_id"],
        "department": staff.get("department"),
        "requested_duration_hours": duration_hours,
        "current_daily_tasks": caps["current_daily_tasks"],
        "current_daily_hours": caps["current_daily_hours"],
        "projected_daily_tasks": projected_tasks,
        "projected_daily_hours": projected_hours,
        "max_daily_tasks": caps["max_daily_tasks"],
        "max_daily_hours": caps["max_daily_hours"],
    }

    if tasks_ok and hours_ok:
        return True, None, details

    reasons: list[str] = []
    if not tasks_ok:
        reasons.append(
            f"dự kiến {projected_tasks} việc/ngày (tối đa {caps['max_daily_tasks']})"
        )
    if not hours_ok:
        reasons.append(
            f"dự kiến {projected_hours:.1f}h/ngày (tối đa {caps['max_daily_hours']}h)"
        )

    trigger_reason = (
        f"Cán bộ {staff['_id']} vượt trần định biên lao động: "
        + "; ".join(reasons)
    )
    return False, trigger_reason, details


async def enforce_workload_capacity(
    staff: dict,
    duration_hours: float,
    db: AsyncIOMotorDatabase,
    *,
    extra_details: dict[str, Any] | None = None,
) -> None:
    """
    Enforce projected workload caps; persist overload_logs then raise 403 if exceeded.
    """
    is_ok, trigger_reason, projection_details = evaluate_workload_capacity(
        staff, duration_hours
    )
    if is_ok:
        return

    log_details = {**projection_details, **(extra_details or {})}
    await create_pending_overload_log(
        db,
        staff_id=staff["_id"],
        trigger_reason=trigger_reason,
        details=log_details,
    )
    raise AppHTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Cán bộ đã chạm trần kịch khung điều kiện lao động.",
        error_code=WORKLOAD_CAP_EXCEEDED,
    )


def check_workload_capacity(staff: dict, duration_hours: float) -> None:
    """
    Sync capacity check without DB logging.

    Prefer enforce_workload_capacity() in API/service paths so overload_logs
    are recorded for manager dashboard and AI suggestions.
    """
    is_ok, _, _ = evaluate_workload_capacity(staff, duration_hours)
    if not is_ok:
        raise AppHTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cán bộ đã chạm trần kịch khung điều kiện lao động.",
            error_code=WORKLOAD_CAP_EXCEEDED,
        )


async def verify_workload_capacity(
    staff_id: str,
    duration_hours: float,
    db: AsyncIOMotorDatabase = Depends(get_database),
) -> dict:
    """
    FastAPI dependency: load staff, enforce projected caps, log overload if exceeded.

    Returns the staff document when capacity is available.
    """
    staff = await db.staffs.find_one({"_id": staff_id})
    if staff is None:
        raise AppHTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Không tìm thấy cán bộ với id '{staff_id}'.",
            error_code="STAFF_NOT_FOUND",
        )

    await enforce_workload_capacity(staff, duration_hours, db)
    return staff


# ============================================================================
# JWT Authentication & Authorization (per 07-authentication-authorization.mdc)
# ============================================================================


def get_current_user(request: Request) -> dict:
    """
    Decode the access JWT from its HttpOnly cookie and return user payload.

    Raises 401 on token error (expired, invalid, malformed).
    """
    token = request.cookies.get(ACCESS_COOKIE_NAME)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Chưa đăng nhập hoặc phiên đăng nhập đã kết thúc",
            headers={"WWW-Authenticate": "Cookie"},
        )
    try:
        return decode_token(token, expected_type="access")
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token đã hết hạn",
            headers={"WWW-Authenticate": "Cookie"},
        )
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token không hợp lệ",
            headers={"WWW-Authenticate": "Cookie"},
        )


def require_role(*allowed_roles: str):
    """
    Dependency factory: check if current user has one of allowed roles.

    Usage:
        @router.get("/protected", dependencies=[Depends(require_role("manager"))])
        async def protected_endpoint():
            ...
    """

    def _check_role(user: dict = Depends(get_current_user)) -> dict:
        if user.get("role") not in allowed_roles:
            raise AppHTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Không đủ quyền thực hiện thao tác này",
                error_code="FORBIDDEN_ACCESS",
            )
        return user

    return _check_role
