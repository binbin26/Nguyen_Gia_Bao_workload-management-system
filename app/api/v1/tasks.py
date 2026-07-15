"""
Tasks API — Tiếp nhận & tạo hồ sơ công việc mới.

Per 03-sau-api-cot-loi.mdc §1 (POST /api/v1/tasks):
- JWT auth, role staff hoặc manager
- Resolve SOP, assign staff greedy, transaction-safe writes
"""

from fastapi import APIRouter, Depends
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from starlette import status

from app.api.dependencies import get_current_user, require_role
from app.core.database import get_database, get_motor_client
from app.core.exceptions import AppHTTPException
from app.repositories.task_repository import create_task
from app.schemas.base_envelope import ApiResponse, success_response
from app.schemas.task import (
    TaskCreateRequest,
    TaskCreateResponse,
    TaskNextStepResponse,
    TaskOut,
)
from app.services.task_service import (
    CATEGORY_NOT_FOUND,
    FORBIDDEN_NOT_ASSIGNEE,
    TASK_ALREADY_CLOSED,
    TASK_INVALID_STATUS,
    TASK_NOT_FOUND,
    advance_task_step,
)

router = APIRouter(prefix="/api/v1/tasks", tags=["tasks"])


@router.post(
    "",
    response_model=ApiResponse[TaskCreateResponse],
    dependencies=[Depends(require_role("staff", "manager"))],
    summary="Tiếp nhận & tạo hồ sơ mới",
    description=(
        "Tạo hồ sơ công việc mới, tự động gán cho cán bộ rảnh nhất trong phòng ban "
        "bước đầu tiên. Nếu toàn bộ phòng ban đạt trần, hồ sơ ở trạng thái "
        "'Chờ xử lý' và ghi overload_log."
    ),
)
async def create_task_endpoint(
    body: TaskCreateRequest,
    user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_database),
    client: AsyncIOMotorClient = Depends(get_motor_client),
) -> ApiResponse[TaskCreateResponse]:
    """
    Tiếp nhận hồ sơ mới và phân bổ nhân sự tự động.

    **Yêu cầu xác thực:** JWT hợp lệ, vai trò `staff` hoặc `manager`.

    **Request body:**
    - `task_code`: Mã quy trình SOP (vd: `B4`, `A1`)

    **Response:** Task vừa tạo kèm `assigned_to` (rỗng nếu chờ xử lý quá tải).
    """
    try:
        task_doc, assigned_to = await create_task(db, client, body.task_code)
    except ValueError as exc:
        if str(exc) == "TASK_CATEGORY_NOT_FOUND":
            raise AppHTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Không tìm thấy quy trình với mã '{body.task_code}'.",
                error_code="TASK_CATEGORY_NOT_FOUND",
            ) from exc
        raise

    task_out = TaskOut.model_validate(task_doc)
    response_data = TaskCreateResponse(task=task_out, assigned_to=assigned_to)

    message = (
        "Hồ sơ đã được tạo và giao việc thành công."
        if assigned_to
        else "Hồ sơ đã được tạo nhưng đang chờ xử lý do phòng ban quá tải."
    )
    return success_response(data=response_data, message=message)


@router.post(
    "/{task_id}/next-step",
    response_model=ApiResponse[TaskNextStepResponse],
    dependencies=[Depends(require_role("staff", "manager"))],
    summary="Luân chuyển bước (State Machine)",
    description=(
        "Hoàn thành bước hiện tại và chuyển sang bước kế tiếp trong quy trình SOP. "
        "Chỉ cán bộ đang được gán hoặc quản lý mới được thao tác. "
        "Toàn bộ ghi DB nằm trong một MongoDB transaction ACID."
    ),
)
async def next_step_endpoint(
    task_id: str,
    user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_database),
    client: AsyncIOMotorClient = Depends(get_motor_client),
) -> ApiResponse[TaskNextStepResponse]:
    """
    Luân chuyển bước công việc theo state machine.

    **Yêu cầu xác thực:** JWT hợp lệ, vai trò `staff` hoặc `manager`.
    `staff` chỉ được gọi khi `staff_id == task.current_assigned_to`.

    **Nhánh kết quả:**
    - Bước cuối → `status = "Hoàn thành"`, `is_locked = true`
    - Còn bước + có nhân sự → gán bước mới, `assigned_to` trả về staff mới
    - Còn bước + phòng ban full → `status = "Tạm dừng"`, tạo `overload_log`
    """
    try:
        task_doc, assigned_to, overload_log_id = await advance_task_step(
            db, client, task_id, user
        )
    except ValueError as exc:
        code = str(exc)
        if code == TASK_NOT_FOUND:
            raise AppHTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Không tìm thấy hồ sơ với id '{task_id}'.",
                error_code=code,
            ) from exc
        if code == TASK_ALREADY_CLOSED:
            raise AppHTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Hồ sơ đã kết thúc, không thể luân chuyển thêm bước.",
                error_code=code,
            ) from exc
        if code == TASK_INVALID_STATUS:
            raise AppHTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Hồ sơ không ở trạng thái 'Đang xử lý', không thể hoàn thành bước.",
                error_code=code,
            ) from exc
        if code == FORBIDDEN_NOT_ASSIGNEE:
            raise AppHTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Bạn không phải người đang xử lý bước này của hồ sơ.",
                error_code=code,
            ) from exc
        if code == CATEGORY_NOT_FOUND:
            raise AppHTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Không tìm thấy quy trình SOP gắn với hồ sơ.",
                error_code=code,
            ) from exc
        raise

    task_out = TaskOut.model_validate(task_doc)
    response_data = TaskNextStepResponse(
        task=task_out,
        assigned_to=assigned_to,
        overload_log_id=overload_log_id,
    )

    if task_doc["status"] == "Hoàn thành":
        message = "Hồ sơ đã hoàn thành toàn bộ quy trình."
    elif task_doc["status"] == "Tạm dừng":
        message = (
            "Bước hiện tại đã hoàn thành nhưng hồ sơ tạm dừng do phòng ban kế tiếp quá tải. "
            "Quản lý cần xử lý qua resolve-overload."
        )
    else:
        message = "Luân chuyển bước thành công."

    return success_response(data=response_data, message=message)
