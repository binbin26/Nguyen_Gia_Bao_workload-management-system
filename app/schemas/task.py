from datetime import datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.staff import Department


class TaskStatus(str, Enum):
    CHO_XU_LY = "Chờ xử lý"
    DANG_XU_LY = "Đang xử lý"
    HOAN_THANH = "Hoàn thành"
    TAM_DUNG = "Tạm dừng"
    HUY = "Hủy"


class TaskMetrics(BaseModel):
    workload_score: float
    step_duration_hours: float
    actual_spent_hours: float | None = None
    rework_count: int = Field(0, ge=0)
    actual_duration_hours: float | None = None
    early_completion_hours: float | None = None
    remaining_step_hours: float | None = None
    last_chunked_date: str | None = None


class WorkflowHistoryEntry(BaseModel):
    step_number: int = Field(..., ge=1)
    department: Department
    assigned_to: str
    status: TaskStatus
    completed_at: datetime | None = None


class ControlFlags(BaseModel):
    is_locked: bool = False
    transfer_count: int = Field(0, ge=0)


class TaskTimestamps(BaseModel):
    created_at: datetime
    due_at: datetime
    completed_at: datetime | None = None


class TaskBase(BaseModel):
    task_code: str
    status: TaskStatus
    current_step: int = Field(..., ge=1)
    current_department: Department
    current_assigned_to: str
    metrics: TaskMetrics
    workflow_history: list[WorkflowHistoryEntry]
    control_flags: ControlFlags
    timestamps: TaskTimestamps


class TaskOut(TaskBase):
    model_config = ConfigDict(populate_by_name=True)

    id: str = Field(alias="_id")


class TaskInDB(TaskOut):
    """Full task document as stored in MongoDB."""

    pass


class TaskCreateRequest(BaseModel):
    task_code: str = Field(..., min_length=1, description="Mã quy trình, vd B4")


class TaskCreateResponse(BaseModel):
    task: TaskOut
    assigned_to: str


class TaskNextStepResponse(BaseModel):
    task: TaskOut
    assigned_to: str = ""
    overload_log_id: str | None = None
