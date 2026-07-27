from fastapi import APIRouter, Depends
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.api.dependencies import get_current_manager
from app.core.database import get_database
from app.repositories.staff_repository import get_staffs
from app.schemas.base_envelope import ApiResponse, success_response
from app.schemas.staff import StaffListResponse, StaffOut

router = APIRouter(prefix="/api/v1/staffs", tags=["staffs"])


@router.get(
    "",
    response_model=ApiResponse[StaffListResponse],
    dependencies=[Depends(get_current_manager)],
    summary="Danh sách toàn bộ nhân sự",
)
async def list_staffs_endpoint(
    db: AsyncIOMotorDatabase = Depends(get_database),
) -> ApiResponse[StaffListResponse]:
    staffs = await get_staffs(db)
    response_data = StaffListResponse(
        staffs=[StaffOut.model_validate(staff) for staff in staffs]
    )
    return success_response(data=response_data)
