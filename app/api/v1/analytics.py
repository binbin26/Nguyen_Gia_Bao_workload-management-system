from typing import Annotated

from fastapi import APIRouter, Depends
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from starlette import status

from app.api.dependencies import get_current_manager
from app.core.database import get_database, get_motor_client
from app.core.exceptions import AppHTTPException
from app.core.roles import AuthenticatedUser
from app.schemas.base_envelope import ApiResponse, success_response
from app.schemas.overload_log import (
    ApplyCapacitySuggestionRequest,
    ManagerActionTaken,
    ResolveOverloadRequest,
)
from app.services.analytics_service import (
    apply_capacity_suggestion,
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
    summary="Cảnh báo điều phối và nhân sự đang quá tải",
)
async def get_pending_overloads(
    db: AsyncIOMotorDatabase = Depends(get_database),
) -> ApiResponse[dict]:
    items = await list_pending_overloads(db)
    return success_response(
        data={"items": items},
        message="Danh sách cảnh báo điều phối và tải lượng hiện tại",
    )


@router.post(
    "/overloads/capacity/{staff_id}/apply",
    response_model=ApiResponse[dict],
    summary="Áp dụng gợi ý cân bằng tải nhân sự",
)
async def apply_capacity_suggestion_endpoint(
    staff_id: str,
    body: ApplyCapacitySuggestionRequest,
    user: Annotated[AuthenticatedUser, Depends(get_current_manager)],
    db: AsyncIOMotorDatabase = Depends(get_database),
    client: AsyncIOMotorClient = Depends(get_motor_client),
) -> ApiResponse[dict]:
    try:
        result = await apply_capacity_suggestion(
            db,
            client,
            staff_id,
            selected_staff_id=body.selected_staff_id,
            resolved_by=user.get("sub") or user.get("staff_id") or "manager",
        )
    except ValueError as exc:
        code = str(exc)
        if code == "STAFF_NOT_FOUND":
            raise AppHTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Không tìm thấy nhân sự nguồn hoặc nhân sự được đề xuất.",
                error_code=code,
            ) from exc
        if code == "STAFF_DEPARTMENT_MISMATCH":
            raise AppHTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Chỉ có thể cân bằng tải giữa nhân sự cùng phòng ban.",
                error_code=code,
            ) from exc
        if code == "STAFF_ALREADY_ASSIGNED":
            raise AppHTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Nhân sự nguồn và nhân sự nhận tải không được trùng nhau.",
                error_code=code,
            ) from exc
        if code == "SOURCE_NOT_OVERLOADED":
            raise AppHTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Tải lượng nguồn đã thay đổi và không còn ở trạng thái quá tải.",
                error_code=code,
            ) from exc
        if code == "NO_TRANSFERABLE_WORKLOAD":
            raise AppHTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Không có đơn vị công việc phù hợp để cân bằng tải.",
                error_code=code,
            ) from exc
        if code == "STAFF_CAPACITY_EXCEEDED":
            raise AppHTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Nhân sự được đề xuất không còn đủ sức chứa tải lượng này.",
                error_code=code,
            ) from exc
        raise

    await websocket_manager.broadcast_json(
        {
            "type": OVERLOAD_RESOLVED_EVENT,
            "payload": {
                "log_id": result["log_id"],
                "source_staff_id": result["source_staff_id"],
                "action_taken": result["action_taken"],
            },
        }
    )
    return success_response(
        data=result,
        message="Đã áp dụng gợi ý cân bằng tải",
    )


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
        if code == "STAFF_CAPACITY_EXCEEDED":
            raise AppHTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Tải lượng nhân sự được chọn đã thay đổi và không còn đủ sức chứa.",
                error_code=code,
            ) from exc
        if code == "STAFF_ALREADY_ASSIGNED":
            raise AppHTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Hồ sơ đã được gán cho nhân sự này.",
                error_code=code,
            ) from exc
        if code == "TASK_NOT_FOUND":
            raise AppHTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Không tìm thấy hồ sơ gắn với cảnh báo.",
                error_code=code,
            ) from exc
        if code == "INVALID_DURATION":
            raise AppHTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Thời lượng hồ sơ không hợp lệ để điều chuyển.",
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
