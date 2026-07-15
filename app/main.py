import logging
from contextlib import asynccontextmanager
from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.config import settings
from app.core.database import (
    close_mongo_connection,
    connect_to_mongo,
    get_database,
    get_motor_client,
)
from app.cron.daily_reset_job import run_daily_reset

logger = logging.getLogger("uvicorn.error")


def register_exception_handlers(app: FastAPI) -> None:
    """Wrap all HTTP and validation errors in the standard ApiResponse envelope."""

    # 2. Thay thế HTTPException bằng StarletteHTTPException để bắt trọn lỗi 404 hệ thống
    @app.exception_handler(StarletteHTTPException)
    async def http_exc_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        # Xác định error_code: Nếu là 404 mặc định thì đặt là "NOT_FOUND" hoặc để None theo thiết kế
        error_code = getattr(exc, "error_code", None)
        if exc.status_code == 404 and not error_code:
            error_code = "NOT_FOUND"

        return JSONResponse(
            status_code=exc.status_code,
            content={
                "success": False,
                "data": None,
                "message": exc.detail,
                "error_code": error_code,
            },
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exc_handler(
        request: Request,
        exc: RequestValidationError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={
                "success": False,
                "data": None,
                "message": "Dữ liệu đầu vào không hợp lệ",
                "error_code": "VALIDATION_ERROR",
            },
        )


@asynccontextmanager
async def lifespan(app: FastAPI):
    await connect_to_mongo()

    async def _run_daily_reset_job() -> None:
        db = get_database()
        client = get_motor_client()
        await run_daily_reset(db, client)

    scheduler = AsyncIOScheduler(timezone=ZoneInfo("Asia/Ho_Chi_Minh"))
    scheduler.add_job(
        _run_daily_reset_job,
        trigger="cron",
        hour=0,
        minute=0,
        timezone=ZoneInfo("Asia/Ho_Chi_Minh"),
        id="daily-reset-job",
        replace_existing=True,
    )
    scheduler.start()
    app.state.scheduler = scheduler
    logger.info(
        "Đã khởi động APScheduler chạy ngầm - Múi giờ: Asia/Ho_Chi_Minh - Lịch chạy: 00:00 hàng ngày"
    )

    try:
        yield
    finally:
        scheduler.shutdown(wait=False)
        await close_mongo_connection()


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.APP_NAME,
        debug=settings.DEBUG,
        lifespan=lifespan,
    )
    register_exception_handlers(app)

    # Include routers
    from app.api.v1 import analytics, dashboard, system, tasks

    app.include_router(dashboard.router)
    app.include_router(tasks.router)
    app.include_router(analytics.router)
    app.include_router(system.router)

    @app.get("/health", tags=["system"])
    async def health_check():
        from app.schemas.base_envelope import ApiResponse

        return ApiResponse(
            success=True,
            data={"status": "ok"},
            message="Service is running",
            error_code=None,
        )

    return app


app = create_app()
