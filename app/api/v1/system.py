from fastapi import APIRouter, Depends, Header
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from starlette import status

from app.core.config import settings
from app.core.database import get_database, get_motor_client
from app.core.exceptions import AppHTTPException
from app.cron.daily_reset_job import run_daily_reset
from app.schemas.base_envelope import ApiResponse, success_response

router = APIRouter(prefix="/api/v1/system", tags=["system"])


def require_internal_secret(
    x_internal_secret: str | None = Header(None, alias="X-Internal-Secret"),
) -> None:
    """Protect the cron endpoint with a shared secret header."""
    expected_secret = settings.CRON_SECRET_KEY or settings.INTERNAL_CRON_SECRET
    if not expected_secret:
        raise AppHTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Cron secret is not configured.",
            error_code="CRON_SECRET_NOT_CONFIGURED",
        )

    if x_internal_secret != expected_secret:
        raise AppHTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: invalid internal secret.",
            error_code="FORBIDDEN_INTERNAL_SECRET",
        )


@router.post(
    "/daily-reset",
    response_model=ApiResponse[dict],
    dependencies=[Depends(require_internal_secret)],
    summary="Trigger daily workload reset",
    description="Reset daily workload counters and chunk active tasks idempotently.",
)
async def trigger_daily_reset(
    db: AsyncIOMotorDatabase = Depends(get_database),
    client: AsyncIOMotorClient = Depends(get_motor_client),
) -> ApiResponse[dict]:
    result = await run_daily_reset(db, client)
    return success_response(
        data=result,
        message="Tái lập tải lượng và chunking công việc đã hoàn tất.",
    )
