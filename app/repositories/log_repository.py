from datetime import datetime, timezone

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.schemas.overload_log import ManagerActionTaken


async def _generate_log_id(
    db: AsyncIOMotorDatabase,
    *,
    session=None,
) -> str:
    """Generate sequential log id: log_YYYYMMDD_NNN."""
    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    prefix = f"log_{today}_"
    count = await db.overload_logs.count_documents(
        {"_id": {"$regex": f"^{prefix}"}},
        session=session,
    )
    return f"{prefix}{count + 1:03d}"


async def create_pending_overload_log(
    db: AsyncIOMotorDatabase,
    staff_id: str,
    trigger_reason: str,
    details: dict | None = None,
    *,
    session=None,
) -> str:
    """
    Persist an overload warning awaiting manager review.

    Returns the generated log _id.
    """
    log_id = await _generate_log_id(db, session=session)
    document = {
        "_id": log_id,
        "timestamp": datetime.now(timezone.utc),
        "staff_id": staff_id,
        "trigger_reason": trigger_reason,
        "manager_action": {
            "action_taken": ManagerActionTaken.PENDING.value,
            "resolved_by": "",
            "details": details or {},
        },
    }
    await db.overload_logs.insert_one(document, session=session)
    return log_id
