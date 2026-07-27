from typing import Annotated

from fastapi import APIRouter, Depends
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from starlette import status

from app.api.dependencies import get_current_manager
from app.core.database import get_database, get_motor_client
from app.core.exceptions import AppHTTPException
from app.core.roles import AuthenticatedUser
from app.schemas.base_envelope import ApiResponse, success_response
from app.schemas.overload_log import ManagerActionTaken, ResolveOverloadRequest
from app.services.analytics_service import (
    list_staff_kpis,
    list_pending_overloads,
    resolve_overload_log,
)
from app.services.websocket_manager import websocket_manager

router = APIRouter(prefix="/api/v1/analytics", tags=["analytics"])

OVERLOAD_RESOLVED_EVENT = "overload.resolved"


@router.get(
    "/staff-kpi",
    response_model=ApiResponse[dict],
    dependencies=[Depends(get_current_manager)],
    summary="KPI nhân sự trong 30 ngày gần nhất",
)
async def get_staff_kpi(
    db: AsyncIOMotorDatabase = Depends(get_database),
) -> ApiResponse[dict]:
    items = await list_staff_kpis(db)
    return success_response(
        data={"items": items, "period_days": 30},
        message="Thống kê KPI nhân sự trong 30 ngày gần nhất",
    )


@router.get(
    "/overloads",
    response_model=ApiResponse[dict],
    dependencies=[Depends(get_current_manager)],
    summary="Danh sách cảnh báo quá tải chờ xử lý",
)
async def get_pending_overloads(
    db: AsyncIOMotorDatabase = Depends(get_database),
) -> ApiResponse[dict]:
    items = await list_pending_overloads(db)
    return success_response(data={"items": items}, message="Danh sách cảnh báo quá tải")


@router.post(
    "/overloads/{log_id}/resolve",
    response_model=ApiResponse[dict],
    summary="Phê duyệt điều chuyển hồ sơ",
)
async def resolve_overload_endpoint(
    log_id: str,
    body: ResolveOverloadRequest,
    user: Annotated[AuthenticatedUser, Depends(get_current_manager)],
    db: AsyncIOMotorDatabase = Depends(get_database),
    client: AsyncIOMotorClient = Depends(get_motor_client),
) -> ApiResponse[dict]:
    try:
        result = await resolve_overload_log(
            db,
            client,
            log_id,
            action_taken=body.action_taken.value,
            selected_staff_id=body.selected_staff_id,
            resolved_by=user.get("sub") or user.get("staff_id") or "manager",
        )
    except ValueError as exc:
        code = str(exc)
        if code == "OVERLOAD_LOG_NOT_FOUND":
            raise AppHTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Không tìm thấy cảnh báo quá tải.",
                error_code=code,
            ) from exc
        if code == "OVERLOAD_LOG_ALREADY_RESOLVED":
            raise AppHTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Cảnh báo này đã được xử lý trước đó.",
                error_code=code,
            ) from exc
        if code == "STAFF_NOT_SELECTED":
            raise AppHTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Vui lòng chọn nhân sự mới khi chấp nhận điều chuyển.",
                error_code=code,
            ) from exc
        if code == "STAFF_NOT_FOUND":
            raise AppHTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Không tìm thấy nhân sự được chỉ định.",
                error_code=code,
            ) from exc
        if code == "STAFF_DEPARTMENT_MISMATCH":
            raise AppHTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Nhân sự được chọn không thuộc phòng ban cùng bước hiện tại.",
                error_code=code,
            ) from exc
        raise

    # The transaction has committed at this point. Notify every connected
    # manager so each browser can invalidate the same REST query cache.
    await websocket_manager.broadcast_json(
        {
            "type": OVERLOAD_RESOLVED_EVENT,
            "payload": {
                "log_id": result["log_id"],
                "task_id": result["task_id"],
                "action_taken": result["action_taken"],
            },
        }
    )

    return success_response(data=result, message="Đã xử lý cảnh báo quá tải")
