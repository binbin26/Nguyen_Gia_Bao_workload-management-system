from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


Department = Literal["A", "B", "C"]


class StaffStatus(str, Enum):
    SAN_SANG = "Sẵn sàng"
    BAN = "Bận"
    QUA_TAI = "Quá tải"
    NGHI_PHEP = "Nghỉ phép"


class WorkloadCaps(BaseModel):
    max_daily_tasks: int = Field(..., ge=1)
    max_daily_hours: float = Field(..., ge=0)
    current_daily_tasks: int = Field(..., ge=0)
    current_daily_hours: float = Field(..., ge=0)


class StaffBase(BaseModel):
    fullname: str
    department: Department
    workload_caps: WorkloadCaps
    status: StaffStatus


class StaffOut(StaffBase):
    model_config = ConfigDict(populate_by_name=True)

    id: str = Field(alias="_id")


class StaffInDB(StaffOut):
    """Full staff document as stored in MongoDB."""

    pass
