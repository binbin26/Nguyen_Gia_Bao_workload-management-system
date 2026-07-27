import logging

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from app.core.config import settings

logger = logging.getLogger("uvicorn.error")

_client: AsyncIOMotorClient | None = None
_db: AsyncIOMotorDatabase | None = None


async def connect_to_mongo() -> None:
    """Initialize Motor client configured for a MongoDB replica set."""
    global _client, _db
    print("--- ĐANG CHẠY HÀM KẾT NỐI DB ---")
    _client = AsyncIOMotorClient(
        settings.MONGO_URI,
        replicaSet=settings.MONGO_REPLICA_SET,
        serverSelectionTimeoutMS=5000,
    )

    await _client.admin.command("ping")
    _db = _client[settings.MONGO_DB_NAME]
    # Refresh sessions are server-revocable. MongoDB's TTL index removes stale
    # records automatically; the compound index supports session cleanup/audit.
    await _db.refresh_sessions.create_index("expires_at", expireAfterSeconds=0)
    await _db.refresh_sessions.create_index([("user_id", 1), ("session_id", 1)])
    # Equality on status followed by the completion-date range supports the
    # first (and most selective) stage of the staff KPI aggregation.
    await _db.tasks.create_index(
        [("status", 1), ("timestamps.completed_at", -1)],
        name="staff_kpi_completed_at_idx",
    )
    try:
            logger.info(
            "Connected to MongoDB replica set '%s', database '%s'",
            settings.MONGO_REPLICA_SET,
            settings.MONGO_DB_NAME,
        )
    except Exception as e:
        logger.error(f"Lỗi khi kết nối đến MongoDB: {e}")


async def close_mongo_connection() -> None:
    """Close the Motor client and release resources."""
    global _client, _db

    if _client is not None:
        _client.close()
        _client = None
        _db = None
        logger.info("MongoDB connection closed")


def get_motor_client() -> AsyncIOMotorClient:
    if _client is None:
        raise RuntimeError("MongoDB client is not initialized. Call connect_to_mongo() first.")
    return _client


def get_database() -> AsyncIOMotorDatabase:
    if _db is None:
        raise RuntimeError("MongoDB database is not initialized. Call connect_to_mongo() first.")
    return _db
