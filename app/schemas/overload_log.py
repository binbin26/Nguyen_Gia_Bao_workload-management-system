from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ManagerActionTaken(str, Enum):
    PENDING = "Pending"
    APPROVED_SUGGESTION = "Approved_Suggestion"
    REJECTED_SUGGESTION = "Rejected_Suggestion"
    MANUAL_OVERRIDE = "Manual_Override"


class ManagerAction(BaseModel):
    action_taken: ManagerActionTaken
    resolved_by: str = ""
    details: dict[str, Any] = Field(default_factory=dict)


class OverloadLogBase(BaseModel):
    timestamp: datetime
    staff_id: str
    trigger_reason: str
    manager_action: ManagerAction


class OverloadLogOut(OverloadLogBase):
    model_config = ConfigDict(populate_by_name=True)

    id: str = Field(alias="_id")


class OverloadLogInDB(OverloadLogOut):
    """Full overload log document as stored in MongoDB."""

    pass


class ResolveOverloadRequest(BaseModel):
    action_taken: ManagerActionTaken
    selected_staff_id: str | None = None


class ApplyCapacitySuggestionRequest(BaseModel):
    """Apply a suggested staff-to-staff workload rebalance."""

    selected_staff_id: str = Field(..., min_length=1)
