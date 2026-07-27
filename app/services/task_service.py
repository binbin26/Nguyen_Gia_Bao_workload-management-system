"""
Task service — state machine transitions for workflow steps.

Per 03-sau-api-cot-loi.mdc §2 (POST /api/v1/tasks/{task_id}/next-step):
- Object-level authorization (assignee or manager)
- Single MongoDB ACID transaction via session.with_transaction()
- Labor protection: early_completion_hours recorded but hours NOT refunded
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from app.core.roles import AuthenticatedUser, RoleEnum
from app.repositories.log_repository import create_pending_overload_log
from app.repositories.task_repository import (
    decrement_staff_task_count,
    get_category_by_task_code,
    get_staffs_by_department,
    get_task_by_id,
    increment_staff_workload,
)
from app.services.assignment_service import pick_best_staff

logger = logging.getLogger(__name__)

TASK_NOT_FOUND = "TASK_NOT_FOUND"
TASK_ALREADY_CLOSED = "TASK_ALREADY_CLOSED"
TASK_INVALID_STATUS = "TASK_INVALID_STATUS"
FORBIDDEN_NOT_ASSIGNEE = "FORBIDDEN_NOT_ASSIGNEE"
CATEGORY_NOT_FOUND = "CATEGORY_NOT_FOUND"

_CLOSED_STATUSES = frozenset({"Hoàn thành", "Hủy"})


def assert_can_complete_step(
    user: AuthenticatedUser,
    task: dict[str, Any],
) -> None:
    """Object-level auth: assignee or manager may advance the current step."""
    if user["role"] == RoleEnum.MANAGER:
        return
    if user.get("staff_id") != task.get("current_assigned_to"):
        raise ValueError(FORBIDDEN_NOT_ASSIGNEE)


def _get_step_started_at(task: dict[str, Any], current_step: int) -> datetime:
    """Infer when the current step began (for actual_duration_hours)."""
    if current_step == 1:
        return task["timestamps"]["created_at"]

    prev_step = current_step - 1
    for entry in task["workflow_history"]:
        if entry["step_number"] == prev_step and entry.get("completed_at"):
            return entry["completed_at"]

    return task["timestamps"]["created_at"]


def _compute_step_metrics(
    task: dict[str, Any],
    current_step: int,
    completed_at: datetime,
) -> tuple[float, float | None]:
    """
    Compute actual_duration_hours and early_completion_hours for the finished step.

    early_completion_hours is recorded when completed_at < due_at (recognition only;
    labor protection forbids reducing current_daily_hours).
    """
    # 1. Đồng bộ completed_at sang UTC-aware nếu nó đang thiếu múi giờ
    if completed_at.tzinfo is None:
        completed_at = completed_at.replace(tzinfo=timezone.utc)

    step_started_at = _get_step_started_at(task, current_step)
    # 2. Đồng bộ step_started_at lấy từ MongoDB sang UTC-aware
    if step_started_at.tzinfo is None:
        step_started_at = step_started_at.replace(tzinfo=timezone.utc)

    actual_hours = max(
        (completed_at - step_started_at).total_seconds() / 3600.0,
        0.0,
    )

    due_at = task["timestamps"]["due_at"]
    # 3. Đồng bộ due_at lấy từ MongoDB sang UTC-aware để so sánh an toàn
    if due_at.tzinfo is None:
        due_at = due_at.replace(tzinfo=timezone.utc)

    early_completion: float | None = None
    if completed_at < due_at:
        early_completion = (due_at - completed_at).total_seconds() / 3600.0

    return actual_hours, early_completion


async def _complete_current_step(
    db: AsyncIOMotorDatabase,
    task: dict[str, Any],
    *,
    session,
) -> tuple[datetime, float, float | None]:
    """Mark the active workflow_history entry as completed; return timing metrics."""
    task_id = task["_id"]
    current_step = task["current_step"]
    completed_at = datetime.now(timezone.utc)

    actual_hours, early_completion = _compute_step_metrics(
        task, current_step, completed_at
    )

    step_update: dict[str, Any] = {
        "workflow_history.$.status": "Hoàn thành",
        "workflow_history.$.completed_at": completed_at,
        "metrics.actual_spent_hours": actual_hours,
        "metrics.actual_duration_hours": actual_hours,
    }
    if early_completion is not None:
        step_update["metrics.early_completion_hours"] = early_completion

    await db.tasks.update_one(
        {"_id": task_id, "workflow_history.step_number": current_step},
        {"$set": step_update},
        session=session,
    )

    logger.info(
        "Task %s step %d completed: actual=%.2fh early=%s",
        task_id,
        current_step,
        actual_hours,
        f"{early_completion:.2f}h" if early_completion is not None else "none",
    )

    return completed_at, actual_hours, early_completion


async def _release_assignee_task_slot(
    db: AsyncIOMotorDatabase,
    staff_id: str,
    *,
    session,
) -> None:
    """
    Decrement current_daily_tasks only — labor protection keeps hours blocked.
    """
    if not staff_id:
        return

    await decrement_staff_task_count(db, staff_id, session=session)
    logger.debug(
        "Released 1 task slot for staff %s (hours unchanged per labor protection)",
        staff_id,
    )


async def advance_task_step(
    db: AsyncIOMotorDatabase,
    client: AsyncIOMotorClient,
    task_id: str,
    user: AuthenticatedUser,
) -> tuple[dict[str, Any], str, str | None]:
    """
    Advance a task to the next workflow step inside one ACID transaction.

    Returns:
        (updated_task_document, assigned_to, overload_log_id_or_none)
    """
    logger.info("next-step requested for task %s by user %s", task_id, user.get("sub"))

    async def _callback(session) -> tuple[dict[str, Any], str, str | None]:
        task = await get_task_by_id(db, task_id, session=session)
        if task is None:
            raise ValueError(TASK_NOT_FOUND)

        if task["status"] in _CLOSED_STATUSES:
            raise ValueError(TASK_ALREADY_CLOSED)

        if task["status"] != "Đang xử lý":
            raise ValueError(TASK_INVALID_STATUS)

        assert_can_complete_step(user, task)

        category = await get_category_by_task_code(
            db, task["task_code"], session=session
        )
        if category is None:
            raise ValueError(CATEGORY_NOT_FOUND)

        workflow_steps: list[dict[str, Any]] = category["workflow_steps"]
        total_steps: int = category["standard_metrics"]["total_steps"]
        current_step: int = task["current_step"]
        previous_assignee: str = task.get("current_assigned_to", "")

        await _complete_current_step(db, task, session=session)
        await _release_assignee_task_slot(db, previous_assignee, session=session)

        # --- Branch A: final step → Hoàn thành ---
        if current_step >= total_steps:
            completed_at = datetime.now(timezone.utc)
            await db.tasks.update_one(
                {"_id": task_id},
                {
                    "$set": {
                        "status": "Hoàn thành",
                        "control_flags.is_locked": True,
                        "timestamps.completed_at": completed_at,
                    }
                },
                session=session,
            )
            logger.info("Task %s reached final step — status set to Hoàn thành", task_id)

            updated = await get_task_by_id(db, task_id, session=session)
            return updated, "", None

        # --- Branch B: more steps remain ---
        next_step_info = workflow_steps[current_step]
        next_dept: str = next_step_info["department"]
        next_duration: float = next_step_info["duration_hours"]
        next_step_number = current_step + 1
        now = datetime.now(timezone.utc)
        new_due_at = now + timedelta(hours=next_duration)

        candidates = await get_staffs_by_department(db, next_dept, session=session)
        selected_staff = pick_best_staff(candidates, next_duration)

        if selected_staff is None:
            # Branch B2: next department fully overloaded → Tạm dừng
            trigger_reason = (
                f"Không thể luân chuyển bước {next_step_number} sang phòng ban "
                f"{next_dept} — toàn bộ nhân sự đã đạt trần"
            )
            log_id = await create_pending_overload_log(
                db,
                staff_id="",
                trigger_reason=trigger_reason,
                details={
                    "task_id": task_id,
                    "task_code": task["task_code"],
                    "current_step": current_step,
                    "next_step": next_step_number,
                    "next_department": next_dept,
                    "requested_duration_hours": next_duration,
                },
                session=session,
            )

            await db.tasks.update_one(
                {"_id": task_id},
                {
                    "$set": {
                        "status": "Tạm dừng",
                        "current_assigned_to": "",
                    }
                },
                session=session,
            )
            logger.warning(
                "Task %s paused at step %d — no eligible staff in dept %s (log %s)",
                task_id,
                next_step_number,
                next_dept,
                log_id,
            )

            updated = await get_task_by_id(db, task_id, session=session)
            return updated, "", log_id

        # Branch B1: assign next step to best staff
        new_staff_id: str = selected_staff["_id"]
        new_history_entry = {
            "step_number": next_step_number,
            "department": next_dept,
            "assigned_to": new_staff_id,
            "status": "Đang xử lý",
            "completed_at": None,
        }

        await db.tasks.update_one(
            {"_id": task_id},
            {
                "$set": {
                    "status": "Đang xử lý",
                    "current_step": next_step_number,
                    "current_department": next_dept,
                    "current_assigned_to": new_staff_id,
                    "timestamps.due_at": new_due_at,
                    "metrics.step_duration_hours": next_duration,
                    "metrics.actual_spent_hours": None,
                    "metrics.actual_duration_hours": None,
                    "metrics.early_completion_hours": None,
                    "metrics.remaining_step_hours": next_duration,
                },
                "$push": {"workflow_history": new_history_entry},
            },
            session=session,
        )

        await increment_staff_workload(
            db,
            new_staff_id,
            next_duration,
            session=session,
        )

        logger.info(
            "Task %s advanced to step %d — assigned to %s in dept %s",
            task_id,
            next_step_number,
            new_staff_id,
            next_dept,
        )

        updated = await get_task_by_id(db, task_id, session=session)
        return updated, new_staff_id, None

    async with await client.start_session() as session:
        return await session.with_transaction(_callback)
