import logging

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from app.core.config import settings

logger = logging.getLogger("uvicorn.error")

_client: AsyncIOMotorClient | None = None
_db: AsyncIOMotorDatabase | None = None


async def connect_to_mongo() -> None:
    """Initialize Motor client configured for a MongoDB replica set."""
    global _client, _db
    _client = AsyncIOMotorClient(
        settings.MONGO_URI,
        replicaSet=settings.MONGO_REPLICA_SET,
        serverSelectionTimeoutMS=5000,
    )

    try:
        await _client.admin.command("ping")
        _db = _client[settings.MONGO_DB_NAME]
        # Refresh sessions are server-revocable. MongoDB's TTL index removes
        # stale records automatically; the compound index supports cleanup.
        await _db.refresh_sessions.create_index("expires_at", expireAfterSeconds=0)
        await _db.refresh_sessions.create_index([("user_id", 1), ("session_id", 1)])
        await _db.tasks.create_index(
            [("status", 1), ("timestamps.completed_at", -1)],
            name="staff_kpi_completed_at_idx",
        )
        # These indexes support the batched alert query: pending events plus
        # active tasks assigned to staff currently at their capacity.
        await _db.overload_logs.create_index(
            [("manager_action.action_taken", 1), ("timestamp", -1)],
            name="pending_overload_timestamp_idx",
        )
        await _db.tasks.create_index(
            [
                ("current_assigned_to", 1),
                ("status", 1),
                ("timestamps.created_at", -1),
            ],
            name="active_tasks_by_staff_idx",
        )
        logger.info(
            "Connected to MongoDB replica set '%s', database '%s'",
            settings.MONGO_REPLICA_SET,
            settings.MONGO_DB_NAME,
        )
    except Exception:
        logger.exception("Could not initialize MongoDB")
        _client.close()
        _client = None
        _db = None
        raise


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
