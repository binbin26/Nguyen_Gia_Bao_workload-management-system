"""
Dashboard API — Real-time workforce monitoring.

Per 03-sau-api-cot-loi.mdc §3 (GET /api/v1/dashboard/summary):
- Read-only, no transaction needed
- Requires JWT auth + manager role only
- Uses MongoDB Aggregation Pipeline (never Python loops)
- Supports optional department filter
"""

from fastapi import APIRouter, Depends, Query
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.api.dependencies import get_current_user, require_role
from app.core.database import get_database
from app.repositories.staff_repository import get_dashboard_summary
from app.schemas.base_envelope import ApiResponse, success_response
from app.schemas.dashboard import DashboardSummaryResponse, DepartmentSummary
from app.schemas.staff import Department

router = APIRouter(prefix="/api/v1/dashboard", tags=["dashboard"])


@router.get(
    "/summary",
    response_model=ApiResponse[DashboardSummaryResponse],
    dependencies=[Depends(require_role("manager"))],
    summary="Giám sát tải lượng phòng ban",
    description="Endpoint thống kê số công việc và giờ làm việc thực tế của toàn bộ nhân viên theo phòng ban. Chỉ manager mới được phép truy cập.",
)
async def get_dashboard_summary_endpoint(
    department: Department = Query(
        None,
        description="Lọc theo phòng ban (A, B, hoặc C). Nếu không truyền, thống kê tất cả phòng.",
    ),
    user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_database),
) -> ApiResponse[DashboardSummaryResponse]:
    """
    Retrieve real-time workload summary per department.

    **Yêu cầu xác thực:**
    - JWT token hợp lệ với role = "manager"

    **Tham số:**
    - department (optional): A, B, hoặc C để lọc phòng ban cụ thể

    **Trả về:**
    Thống kê chi tiết gồm:
    - total_tasks: Tổng số công việc đang xử lý
    - total_hours: Tổng số giờ làm việc dự kiến
    - staff_count: Số lượng nhân viên
    - avg_hours: Trung bình giờ/nhân viên
    - by_status: Phân bố nhân viên theo trạng thái (Sẵn sàng, Bận, v.v.)

    **Ví dụ gọi API:**
    ```
    GET /api/v1/dashboard/summary?department=B
    Cookie: __Host-access_token=<HttpOnly JWT do trình duyệt tự gửi>
    ```

    **Response (200 OK):**
    ```json
    {
      "success": true,
      "data": {
        "summary": [
          {
            "department": "B",
            "total_tasks": 8,
            "total_hours": 11.5,
            "staff_count": 4,
            "avg_hours": 2.875,
            "by_status": [
              {"status": "Sẵn sàng", "count": 2},
              {"status": "Bận", "count": 1},
              {"status": "Quá tải", "count": 1}
            ]
          }
        ]
      },
      "message": null,
      "error_code": null
    }
    ```
    """
    # Query aggregation từ database (không dùng loop Python)
    result = await get_dashboard_summary(db, department)

    # Chuyển đổi kết quả sang schema
    summaries = [
        DepartmentSummary(**item) for item in result
    ]

    response_data = DashboardSummaryResponse(summary=summaries)
    return success_response(data=response_data)
