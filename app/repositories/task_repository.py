"""
Task repository — MongoDB Motor operations for task creation and queries.

Per 03-sau-api-cot-loi.mdc §1 (POST /api/v1/tasks):
- Resolve SOP from task_categories
- Assign staff via greedy pick_best_staff
- Persist task + $inc workload in a single transaction
- Create overload_log when no eligible staff remains
"""

from datetime import datetime, timedelta, timezone
from typing import Any

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from app.repositories.log_repository import create_pending_overload_log
from app.services.assignment_service import pick_best_staff


async def generate_task_id(
    db: AsyncIOMotorDatabase,
    *,
    session=None,
) -> str:
    """Generate sequential task id: task_YYYYMMDD_XXXX."""
    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    prefix = f"task_{today}_"
    count = await db.tasks.count_documents(
        {"_id": {"$regex": f"^{prefix}"}},
        session=session,
    )
    return f"{prefix}{count + 1:04d}"


async def get_category_by_task_code(
    db: AsyncIOMotorDatabase,
    task_code: str,
    *,
    session=None,
) -> dict[str, Any] | None:
    """Load SOP template by task_code."""
    return await db.task_categories.find_one(
        {"task_code": task_code},
        session=session,
    )


async def get_staffs_by_department(
    db: AsyncIOMotorDatabase,
    department: str,
    *,
    session=None,
) -> list[dict[str, Any]]:
    """Return all staff documents in the given department."""
    cursor = db.staffs.find({"department": department}, session=session)
    return await cursor.to_list(length=None)


async def get_task_by_id(
    db: AsyncIOMotorDatabase,
    task_id: str,
    *,
    session=None,
) -> dict[str, Any] | None:
    """Load a task document by _id."""
    return await db.tasks.find_one({"_id": task_id}, session=session)


async def decrement_staff_task_count(
    db: AsyncIOMotorDatabase,
    staff_id: str,
    *,
    session=None,
) -> None:
    """
    Release one daily task slot for the staff member.

    Labor protection: only decrements current_daily_tasks, never current_daily_hours.
    """
    await db.staffs.update_one(
        {"_id": staff_id},
        {"$inc": {"workload_caps.current_daily_tasks": -1}},
        session=session,
    )


async def increment_staff_workload(
    db: AsyncIOMotorDatabase,
    staff_id: str,
    duration_hours: float,
    *,
    session=None,
) -> None:
    """Atomically reserve capacity for the assigned staff member."""
    await db.staffs.update_one(
        {"_id": staff_id},
        {
            "$inc": {
                "workload_caps.current_daily_tasks": 1,
                "workload_caps.current_daily_hours": duration_hours,
            }
        },
        session=session,
    )


def _build_task_document(
    *,
    task_id: str,
    task_code: str,
    department: str,
    duration_hours: float,
    workload_score: float,
    assigned_staff_id: str,
    status: str,
    created_at: datetime,
    due_at: datetime,
) -> dict[str, Any]:
    """Assemble a tasks collection document matching MongoDB JSON Schema."""
    return {
        "_id": task_id,
        "task_code": task_code,
        "status": status,
        "current_step": 1,
        "current_department": department,
        "current_assigned_to": assigned_staff_id,
        "metrics": {
            "workload_score": workload_score,
            "step_duration_hours": duration_hours,
            "actual_duration_hours": None,
            "early_completion_hours": None,
            "remaining_step_hours": duration_hours,
            "last_chunked_date": None,
        },
        "workflow_history": [
            {
                "step_number": 1,
                "department": department,
                "assigned_to": assigned_staff_id,
                "status": status,
                "completed_at": None,
            }
        ],
        "control_flags": {"is_locked": False, "transfer_count": 0},
        "timestamps": {
            "created_at": created_at,
            "due_at": due_at,
            "completed_at": None,
        },
    }


async def create_task(
    db: AsyncIOMotorDatabase,
    client: AsyncIOMotorClient,
    task_code: str,
) -> tuple[dict[str, Any], str]:
    """
    Create a new task with automatic staff assignment.

    Returns:
        (task_document, assigned_to) where assigned_to is staff _id or "" if waiting.
    """
    category = await get_category_by_task_code(db, task_code)
    if category is None:
        raise ValueError("TASK_CATEGORY_NOT_FOUND")

    first_step = category["workflow_steps"][0]
    department: str = first_step["department"]
    duration_hours: float = first_step["duration_hours"]
    workload_score: float = category["standard_metrics"]["workload_score"]

    candidates = await get_staffs_by_department(db, department)
    selected_staff = pick_best_staff(candidates, duration_hours)

    created_at = datetime.now(timezone.utc)
    due_at = created_at + timedelta(hours=duration_hours)

    if selected_staff is not None:
        status = "Đang xử lý"
        assigned_staff_id = selected_staff["_id"]
    else:
        status = "Chờ xử lý"
        assigned_staff_id = ""

    async def _callback(session) -> tuple[dict[str, Any], str]:
        task_id = await generate_task_id(db, session=session)
        task_doc = _build_task_document(
            task_id=task_id,
            task_code=task_code,
            department=department,
            duration_hours=duration_hours,
            workload_score=workload_score,
            assigned_staff_id=assigned_staff_id,
            status=status,
            created_at=created_at,
            due_at=due_at,
        )

        await db.tasks.insert_one(task_doc, session=session)

        if selected_staff is not None:
            await increment_staff_workload(
                db,
                assigned_staff_id,
                duration_hours,
                session=session,
            )
        else:
            await create_pending_overload_log(
                db,
                staff_id="",
                trigger_reason=(
                    f"Toàn bộ phòng ban {department} đã đạt trần định biên"
                ),
                details={
                    "task_id": task_id,
                    "task_code": task_code,
                    "department": department,
                    "requested_duration_hours": duration_hours,
                },
                session=session,
            )

        return task_doc, assigned_staff_id

    async with await client.start_session() as session:
        return await session.with_transaction(_callback)
