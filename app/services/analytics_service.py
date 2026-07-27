from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from app.repositories.task_repository import get_task_by_id
from app.schemas.overload_log import ManagerActionTaken

logger = logging.getLogger(__name__)

KPI_WINDOW_DAYS = 30


def build_staff_kpi_pipeline(
    period_start: datetime,
    period_end: datetime,
) -> list[dict[str, Any]]:
    """Build the MongoDB-only aggregation used by the manager KPI dashboard.

    Numeric fields are converted defensively so one malformed legacy task cannot
    fail the whole report. ``actual_duration_hours`` is kept as a temporary
    fallback while existing records are migrated to ``actual_spent_hours``.
    """
    return [
        {
            "$match": {
                "status": "Hoàn thành",
                "timestamps.completed_at": {
                    "$gte": period_start,
                    "$lte": period_end,
                },
            }
        },
        {
            "$set": {
                "_standard_hours": {
                    "$max": [
                        0,
                        {
                            "$convert": {
                                "input": "$metrics.step_duration_hours",
                                "to": "double",
                                "onError": 0,
                                "onNull": 0,
                            }
                        },
                    ]
                },
                "_actual_hours": {
                    "$max": [
                        0,
                        {
                            "$convert": {
                                "input": {
                                    "$ifNull": [
                                        "$metrics.actual_spent_hours",
                                        "$metrics.actual_duration_hours",
                                    ]
                                },
                                "to": "double",
                                "onError": 0,
                                "onNull": 0,
                            }
                        },
                    ]
                },
                "_rework_count": {
                    "$max": [
                        0,
                        {
                            "$convert": {
                                "input": "$metrics.rework_count",
                                "to": "int",
                                "onError": 0,
                                "onNull": 0,
                            }
                        },
                    ]
                },
            }
        },
        {
            "$group": {
                "_id": "$current_assigned_to",
                "total_tasks": {"$sum": 1},
                "total_standard_hours": {"$sum": "$_standard_hours"},
                "total_actual_hours": {"$sum": "$_actual_hours"},
                "total_rework_count": {"$sum": "$_rework_count"},
                "reworked_tasks": {
                    "$sum": {"$cond": [{"$gt": ["$_rework_count", 0]}, 1, 0]}
                },
            }
        },
        # Invalid legacy tasks must not become a synthetic "unknown employee" row.
        {"$match": {"_id": {"$nin": [None, ""]}}},
        {
            "$lookup": {
                "from": "staffs",
                "localField": "_id",
                "foreignField": "_id",
                "as": "staff",
            }
        },
        {"$set": {"staff": {"$first": "$staff"}}},
        {
            "$set": {
                "efficiency_rate": {
                    "$cond": [
                        {"$gt": ["$total_actual_hours", 0]},
                        {
                            "$round": [
                                {
                                    "$multiply": [
                                        {
                                            "$divide": [
                                                "$total_standard_hours",
                                                "$total_actual_hours",
                                            ]
                                        },
                                        100,
                                    ]
                                },
                                2,
                            ]
                        },
                        0,
                    ]
                },
                "rework_rate": {
                    "$round": [
                        {
                            "$multiply": [
                                {"$divide": ["$reworked_tasks", "$total_tasks"]},
                                100,
                            ]
                        },
                        2,
                    ]
                },
            }
        },
        {
            "$project": {
                "_id": 0,
                "staff_id": "$_id",
                "staff_name": {"$ifNull": ["$staff.fullname", "$_id"]},
                "department": {"$ifNull": ["$staff.department", None]},
                "total_tasks": 1,
                "total_standard_hours": {"$round": ["$total_standard_hours", 2]},
                "total_actual_hours": {"$round": ["$total_actual_hours", 2]},
                "efficiency_rate": 1,
                "reworked_tasks": 1,
                "total_rework_count": 1,
                "rework_rate": 1,
                "quality_score": {
                    "$round": [{"$subtract": [100, "$rework_rate"]}, 2]
                },
            }
        },
        {"$sort": {"efficiency_rate": -1, "total_tasks": -1, "staff_name": 1}},
    ]


async def list_staff_kpis(
    db: AsyncIOMotorDatabase,
    *,
    now: datetime | None = None,
) -> list[dict[str, Any]]:
    """Return pre-calculated KPI rows for completed tasks in the last 30 days."""
    period_end = now or datetime.now(timezone.utc)
    if period_end.tzinfo is None:
        period_end = period_end.replace(tzinfo=timezone.utc)
    period_start = period_end - timedelta(days=KPI_WINDOW_DAYS)

    pipeline = build_staff_kpi_pipeline(period_start, period_end)
    cursor = db.tasks.aggregate(pipeline, allowDiskUse=True)
    return await cursor.to_list(length=None)


def build_staff_suggestions(
    candidates: list[dict[str, Any]],
    duration_hours: float,
) -> list[dict[str, Any]]:
    """Return ranked replacement suggestions for a pending overload alert."""
    eligible = [
        staff
        for staff in candidates
        if staff.get("status") != "Nghỉ phép"
        and _can_accept_projected_workload(staff, duration_hours)
    ]

    suggestions = []
    for staff in eligible:
        caps = staff["workload_caps"]
        max_hours = caps.get("max_daily_hours") or 0.0
        matching_score = 0.0
        if max_hours > 0:
            matching_score = 1.0 - (caps["current_daily_hours"] / max_hours)

        suggestions.append(
            {
                "staff_id": staff["_id"],
                "fullname": staff.get("fullname", staff["_id"]),
                "department": staff.get("department"),
                "current_daily_tasks": caps["current_daily_tasks"],
                "current_daily_hours": caps["current_daily_hours"],
                "matching_score": round(matching_score, 4),
            }
        )

    suggestions.sort(key=lambda item: item["matching_score"], reverse=True)
    return suggestions


def _can_accept_projected_workload(staff: dict[str, Any], duration_hours: float) -> bool:
    caps = staff["workload_caps"]
    projected_tasks = caps["current_daily_tasks"] + 1
    projected_hours = caps["current_daily_hours"] + duration_hours
    return (
        projected_tasks <= caps["max_daily_tasks"]
        and projected_hours <= caps["max_daily_hours"]
    )


async def list_pending_overloads(
    db: AsyncIOMotorDatabase,
) -> list[dict[str, Any]]:
    """Load pending overload alerts with task context and replacement suggestions."""
    cursor = db.overload_logs.find(
        {"manager_action.action_taken": ManagerActionTaken.PENDING.value}
    )
    logs = await cursor.to_list(length=None)

    items = []
    for log in logs:
        details = log.get("manager_action", {}).get("details", {}) or {}
        task_id = details.get("task_id")
        task = None
        if task_id:
            task = await get_task_by_id(db, task_id)

        duration_hours = None
        if details.get("requested_duration_hours") is not None:
            duration_hours = float(details["requested_duration_hours"])
        elif task is not None:
            duration_hours = task.get("metrics", {}).get("step_duration_hours")

        suggestions = []
        if task is not None and task.get("current_department"):
            candidates = await db.staffs.find(
                {"department": task["current_department"]},
                {"_id": 1, "fullname": 1, "department": 1, "status": 1, "workload_caps": 1},
            ).to_list(length=None)
            suggestions = build_staff_suggestions(
                candidates,
                float(duration_hours or 0.0),
            )

        items.append(
            {
                "_id": log["_id"],
                "timestamp": log.get("timestamp"),
                "staff_id": log.get("staff_id"),
                "trigger_reason": log.get("trigger_reason"),
                "task": {
                    "task_id": task_id,
                    "task_code": task.get("task_code") if task else None,
                    "status": task.get("status") if task else None,
                    "current_department": task.get("current_department") if task else None,
                    "current_step": task.get("current_step") if task else None,
                    "current_assigned_to": task.get("current_assigned_to") if task else None,
                },
                "suggestions": suggestions,
            }
        )

    return items


async def resolve_overload_log(
    db: AsyncIOMotorDatabase,
    client: AsyncIOMotorClient,
    log_id: str,
    *,
    action_taken: str,
    selected_staff_id: str | None,
    resolved_by: str,
) -> dict[str, Any]:
    """Resolve a pending overload alert inside a single ACID transaction."""

    async def _callback(session) -> dict[str, Any]:
        log = await db.overload_logs.find_one({"_id": log_id}, session=session)
        if log is None:
            raise ValueError("OVERLOAD_LOG_NOT_FOUND")

        current_action = log.get("manager_action", {}).get("action_taken")
        if current_action != ManagerActionTaken.PENDING.value:
            raise ValueError("OVERLOAD_LOG_ALREADY_RESOLVED")

        details = log.get("manager_action", {}).get("details", {}) or {}
        task_id = details.get("task_id")
        if not task_id:
            raise ValueError("TASK_NOT_FOUND")

        task = await get_task_by_id(db, task_id, session=session)
        if task is None:
            raise ValueError("TASK_NOT_FOUND")

        action_enum = ManagerActionTaken(action_taken)
        status_update: dict[str, Any] = {
            "manager_action.action_taken": action_enum.value,
            "manager_action.resolved_by": resolved_by,
            "manager_action.details": {
                **details,
                "resolved_at": datetime.now(timezone.utc),
                "resolved_by": resolved_by,
                "selected_staff_id": selected_staff_id,
                "action_taken": action_enum.value,
            },
        }

        if action_enum in {
            ManagerActionTaken.APPROVED_SUGGESTION,
            ManagerActionTaken.MANUAL_OVERRIDE,
        }:
            if not selected_staff_id:
                raise ValueError("STAFF_NOT_SELECTED")

            staff = await db.staffs.find_one({"_id": selected_staff_id}, session=session)
            if staff is None:
                raise ValueError("STAFF_NOT_FOUND")

            if staff.get("department") != task.get("current_department"):
                raise ValueError("STAFF_DEPARTMENT_MISMATCH")

            duration_hours = details.get("requested_duration_hours")
            if duration_hours is None:
                duration_hours = task.get("metrics", {}).get("step_duration_hours")
            if duration_hours is None:
                raise ValueError("INVALID_DURATION")

            previous_staff_id = task.get("current_assigned_to")
            if previous_staff_id and previous_staff_id != selected_staff_id:
                await db.staffs.update_one(
                    {"_id": previous_staff_id},
                    {
                        "$inc": {
                            "workload_caps.current_daily_tasks": -1,
                            "workload_caps.current_daily_hours": -float(duration_hours),
                        }
                    },
                    session=session,
                )

            await db.staffs.update_one(
                {"_id": selected_staff_id},
                {
                    "$inc": {
                        "workload_caps.current_daily_tasks": 1,
                        "workload_caps.current_daily_hours": float(duration_hours),
                    }
                },
                session=session,
            )

            task_status = task.get("status")
            task_update: dict[str, Any] = {
                "current_assigned_to": selected_staff_id,
                "control_flags.transfer_count": (task.get("control_flags", {}).get("transfer_count", 0) + 1),
            }
            if task_status in {"Tạm dừng", "Chờ xử lý"}:
                task_update["status"] = "Đang xử lý"

            await db.tasks.update_one(
                {"_id": task_id},
                {"$set": task_update},
                session=session,
            )

            current_step = task.get("current_step")
            if current_step is not None:
                await db.tasks.update_one(
                    {"_id": task_id, "workflow_history.step_number": current_step},
                    {"$set": {"workflow_history.$.assigned_to": selected_staff_id}},
                    session=session,
                )

        await db.overload_logs.update_one(
            {"_id": log_id},
            {"$set": status_update},
            session=session,
        )

        updated_log = await db.overload_logs.find_one({"_id": log_id}, session=session)
        return {
            "log_id": log_id,
            "action_taken": action_enum.value,
            "resolved_by": resolved_by,
            "task_id": task_id,
            "task_status": task.get("status"),
            "updated_log": updated_log,
        }

    async with await client.start_session() as session:
        return await session.with_transaction(_callback)
