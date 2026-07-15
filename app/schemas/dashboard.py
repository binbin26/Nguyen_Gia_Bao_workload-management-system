"""
Schema định nghĩa response cho Dashboard API.
"""

from pydantic import BaseModel, Field
from typing import Optional

from app.schemas.staff import Department


class StatusCount(BaseModel):
    """Số lượng nhân viên theo từng trạng thái."""

    status: str = Field(..., description="Trạng thái nhân viên")
    count: int = Field(..., ge=0, description="Số lượng nhân viên")


class DepartmentSummary(BaseModel):
    """Thống kê tải lượng của một phòng ban."""

    department: str = Field(..., alias="_id", description="Mã phòng ban (A/B/C)")
    total_tasks: int = Field(..., ge=0, description="Tổng số công việc đang xử lý")
    total_hours: float = Field(..., ge=0, description="Tổng số giờ làm việc dự kiến")
    staff_count: int = Field(..., ge=0, description="Số lượng nhân viên")
    avg_hours: float = Field(..., ge=0, description="Trung bình giờ làm việc/nhân viên")
    by_status: list[StatusCount] = Field(
        default_factory=list, description="Phân bố nhân viên theo trạng thái"
    )


class DashboardSummaryResponse(BaseModel):
    """Tổng hợp thông tin giám sát tải lượng toàn công ty hoặc một phòng ban."""

    summary: list[DepartmentSummary] = Field(
        ..., description="Danh sách phòng ban với thống kê"
    )
