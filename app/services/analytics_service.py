from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from app.repositories.log_repository import create_pending_overload_log
from app.repositories.staff_repository import get_staffs
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
    *,
    task_count: int = 1,
    keep_below_hours_cap: bool = False,
) -> list[dict[str, Any]]:
    """Return ranked replacement suggestions for a pending overload alert."""
    eligible = [
        staff
        for staff in candidates
        if staff.get("status") != "Nghỉ phép"
        and _can_accept_projected_workload(
            staff,
            duration_hours,
            task_count=task_count,
            keep_below_hours_cap=keep_below_hours_cap,
        )
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
                "status": staff.get("status"),
                "current_daily_tasks": caps["current_daily_tasks"],
                "current_daily_hours": caps["current_daily_hours"],
                "max_daily_tasks": caps["max_daily_tasks"],
                "max_daily_hours": caps["max_daily_hours"],
                "projected_daily_tasks": caps["current_daily_tasks"] + task_count,
                "projected_daily_hours": round(
                    caps["current_daily_hours"] + duration_hours,
                    2,
                ),
                "transfer_daily_tasks": task_count,
                "transfer_daily_hours": round(duration_hours, 2),
                "matching_score": round(matching_score, 4),
            }
        )

    suggestions.sort(key=lambda item: item["matching_score"], reverse=True)
    return suggestions


def _can_accept_projected_workload(
    staff: dict[str, Any],
    duration_hours: float,
    *,
    task_count: int = 1,
    keep_below_hours_cap: bool = False,
) -> bool:
    caps = staff["workload_caps"]
    projected_tasks = caps["current_daily_tasks"] + task_count
    projected_hours = caps["current_daily_hours"] + duration_hours
    tasks_ok = projected_tasks <= caps["max_daily_tasks"]
    hours_ok = projected_hours <= caps["max_daily_hours"]
    if keep_below_hours_cap:
        hours_ok = projected_hours < caps["max_daily_hours"]
    return tasks_ok and hours_ok


def is_staff_overloaded(staff: dict[str, Any]) -> bool:
    """Mirror the canonical MongoDB workload-status rule in Python."""
    caps = staff["workload_caps"]
    return (
        caps["current_daily_tasks"] > caps["max_daily_tasks"]
        or caps["current_daily_hours"] >= caps["max_daily_hours"]
    )


def calculate_capacity_transfer(staff: dict[str, Any]) -> dict[str, int | float]:
    """Calculate the smallest auditable workload unit that relieves overload.

    Capacity snapshots may originate from aggregate counters without a concrete
    active task.  In that case we rebalance one or more average task units and
    record the exact counter adjustment in ``overload_logs``.
    """
    caps = staff["workload_caps"]
    current_tasks = int(caps["current_daily_tasks"])
    current_hours = float(caps["current_daily_hours"])
    max_tasks = int(caps["max_daily_tasks"])
    max_hours = float(caps["max_daily_hours"])

    if current_tasks <= 0:
        raise ValueError("NO_TRANSFERABLE_WORKLOAD")

    transfer_tasks = max(1, current_tasks - max_tasks)
    average_task_hours = current_hours / current_tasks
    hours_needed_below_cap = (
        max(current_hours - max_hours, 0.0) + 0.01
        if current_hours >= max_hours
        else 0.0
    )
    transfer_hours = min(
        current_hours,
        max(average_task_hours * transfer_tasks, hours_needed_below_cap),
    )

    return {
        "daily_tasks": transfer_tasks,
        "daily_hours": round(transfer_hours, 2),
    }


async def list_pending_overloads(
    db: AsyncIOMotorDatabase,
) -> list[dict[str, Any]]:
    """Return persisted pending events plus the current overload snapshot.

    ``overload_logs`` is an event/history collection.  It cannot be the sole
    source for a live dashboard because an event may already be resolved while
    a staff member remains at capacity, and legacy/seed data may never have
    emitted an event.  This function intentionally combines:

    * actionable, persisted Pending events; and
    * informational staff-capacity alerts derived from normalized counters.

    Staff and task data are loaded in batches to avoid the former N+1 query
    pattern (one task query and one candidate query per log).
    """
    logs = await db.overload_logs.find(
        {"manager_action.action_taken": ManagerActionTaken.PENDING.value}
    ).sort("timestamp", -1).to_list(length=None)

    staffs = await get_staffs(db)
    staff_by_id = {staff["_id"]: staff for staff in staffs}
    overloaded_staffs = [
        staff for staff in staffs if staff.get("status") == "Quá tải"
    ]

    logged_task_ids = {
        details.get("task_id")
        for log in logs
        if (
            details := (log.get("manager_action", {}).get("details", {}) or {})
        ).get("task_id")
    }
    overloaded_staff_ids = {staff["_id"] for staff in overloaded_staffs}

    task_filters: list[dict[str, Any]] = []
    if logged_task_ids:
        task_filters.append({"_id": {"$in": sorted(logged_task_ids)}})
    if overloaded_staff_ids:
        task_filters.append(
            {
                "current_assigned_to": {"$in": sorted(overloaded_staff_ids)},
                "status": {"$in": ["Đang xử lý", "Chờ xử lý", "Tạm dừng"]},
            }
        )

    tasks: list[dict[str, Any]] = []
    if task_filters:
        task_query = task_filters[0] if len(task_filters) == 1 else {"$or": task_filters}
        tasks = await db.tasks.find(
            task_query,
            {
                "_id": 1,
                "task_code": 1,
                "status": 1,
                "current_department": 1,
                "current_step": 1,
                "current_assigned_to": 1,
                "metrics.step_duration_hours": 1,
                "timestamps.created_at": 1,
            },
        ).sort("timestamps.created_at", -1).to_list(length=None)

    task_by_id = {task["_id"]: task for task in tasks}
    active_task_by_staff: dict[str, dict[str, Any]] = {}
    for task in tasks:
        assigned_to = task.get("current_assigned_to")
        if assigned_to and assigned_to not in active_task_by_staff:
            active_task_by_staff[assigned_to] = task

    staffs_by_department: dict[str, list[dict[str, Any]]] = {}
    for staff in staffs:
        staffs_by_department.setdefault(staff.get("department", ""), []).append(staff)

    def _task_context(
        task: dict[str, Any] | None,
        task_id: str | None,
        target_department: str | None,
    ) -> dict[str, Any]:
        return {
            "task_id": task_id,
            "task_code": task.get("task_code") if task else None,
            "status": task.get("status") if task else None,
            # For a blocked next step the target department in log details is
            # more accurate than a legacy task's previous current_department.
            "current_department": target_department
            or (task.get("current_department") if task else None),
            "current_step": task.get("current_step") if task else None,
            "current_assigned_to": (
                task.get("current_assigned_to") if task else None
            ),
        }

    items: list[dict[str, Any]] = []
    pending_staff_ids: set[str] = set()

    for log in logs:
        manager_action = log.get("manager_action", {}) or {}
        details = manager_action.get("details", {}) or {}
        staff_id = log.get("staff_id") or ""
        if staff_id:
            pending_staff_ids.add(staff_id)

        task_id = details.get("task_id")
        task = task_by_id.get(task_id)
        duration_hours = details.get("requested_duration_hours")
        if duration_hours is None and task is not None:
            duration_hours = task.get("metrics", {}).get("step_duration_hours")
        duration_hours = float(duration_hours or 0.0)

        department = (
            details.get("next_department")
            or details.get("department")
            or (task.get("current_department") if task else None)
            or (staff_by_id.get(staff_id, {}).get("department") if staff_id else None)
        )
        suggestions = build_staff_suggestions(
            staffs_by_department.get(department or "", []),
            duration_hours,
        )
        staff = staff_by_id.get(staff_id)

        items.append(
            {
                "_id": log["_id"],
                "alert_type": "assignment_blocked",
                "resolvable": bool(task_id and task),
                "timestamp": log.get("timestamp"),
                "staff_id": staff_id,
                "staff_name": staff.get("fullname") if staff else None,
                "department": department,
                "trigger_reason": log.get("trigger_reason"),
                "action_taken": manager_action.get("action_taken"),
                "manager_action": manager_action,
                "task": _task_context(task, task_id, department),
                "suggestions": suggestions,
            }
        )

    for staff in overloaded_staffs:
        staff_id = staff["_id"]
        if staff_id in pending_staff_ids:
            continue

        caps = staff["workload_caps"]
        task = active_task_by_staff.get(staff_id)
        task_id = task.get("_id") if task else None
        department = staff.get("department")
        try:
            suggested_transfer = calculate_capacity_transfer(staff)
        except ValueError:
            suggested_transfer = None

        suggestions = []
        if suggested_transfer:
            suggestions = build_staff_suggestions(
                staffs_by_department.get(department or "", []),
                float(suggested_transfer["daily_hours"]),
                task_count=int(suggested_transfer["daily_tasks"]),
                # Applying a balancing suggestion must not merely move the
                # overload alert from the source employee to the target.
                keep_below_hours_cap=True,
            )

        items.append(
            {
                "_id": f"capacity:{staff_id}",
                "alert_type": "staff_capacity",
                "resolvable": bool(suggestions),
                "timestamp": None,
                "staff_id": staff_id,
                "staff_name": staff.get("fullname", staff_id),
                "department": department,
                "trigger_reason": (
                    f"Đã chạm trần tải lượng: "
                    f"{caps['current_daily_tasks']}/{caps['max_daily_tasks']} tác vụ, "
                    f"{caps['current_daily_hours']:.1f}/{caps['max_daily_hours']:.1f} giờ."
                ),
                "action_taken": ManagerActionTaken.PENDING.value,
                "manager_action": {
                    "action_taken": ManagerActionTaken.PENDING.value,
                    "resolved_by": "",
                    "details": {"source": "staff_workload_snapshot"},
                },
                "workload_caps": caps,
                "suggested_transfer": suggested_transfer,
                "task": _task_context(task, task_id, department),
                "suggestions": suggestions,
            }
        )

    return items


def _status_for_caps(caps: dict[str, Any], existing_status: str | None) -> str:
    """Keep the legacy physical status reasonably synchronized after a write."""
    if existing_status == "Nghỉ phép":
        return "Nghỉ phép"
    if (
        caps["current_daily_tasks"] > caps["max_daily_tasks"]
        or caps["current_daily_hours"] >= caps["max_daily_hours"]
    ):
        return "Quá tải"
    if caps["current_daily_tasks"] > 0 or caps["current_daily_hours"] > 0:
        return "Bận"
    return "Sẵn sàng"


async def apply_capacity_suggestion(
    db: AsyncIOMotorDatabase,
    client: AsyncIOMotorClient,
    overloaded_staff_id: str,
    *,
    selected_staff_id: str,
    resolved_by: str,
) -> dict[str, Any]:
    """Apply an AI capacity suggestion and persist an auditable decision log."""
    if overloaded_staff_id == selected_staff_id:
        raise ValueError("STAFF_ALREADY_ASSIGNED")

    async def _callback(session) -> dict[str, Any]:
        source = await db.staffs.find_one(
            {"_id": overloaded_staff_id},
            session=session,
        )
        if source is None:
            raise ValueError("STAFF_NOT_FOUND")

        target = await db.staffs.find_one(
            {"_id": selected_staff_id},
            session=session,
        )
        if target is None:
            raise ValueError("STAFF_NOT_FOUND")

        if source.get("department") != target.get("department"):
            raise ValueError("STAFF_DEPARTMENT_MISMATCH")
        if target.get("status") == "Nghỉ phép":
            raise ValueError("STAFF_CAPACITY_EXCEEDED")
        if not is_staff_overloaded(source):
            raise ValueError("SOURCE_NOT_OVERLOADED")

        transfer = calculate_capacity_transfer(source)
        transfer_tasks = int(transfer["daily_tasks"])
        transfer_hours = float(transfer["daily_hours"])

        if not _can_accept_projected_workload(
            target,
            transfer_hours,
            task_count=transfer_tasks,
            keep_below_hours_cap=True,
        ):
            raise ValueError("STAFF_CAPACITY_EXCEEDED")

        source_caps = source["workload_caps"]
        target_caps = target["workload_caps"]
        source_after = {
            **source_caps,
            "current_daily_tasks": source_caps["current_daily_tasks"] - transfer_tasks,
            "current_daily_hours": round(
                source_caps["current_daily_hours"] - transfer_hours,
                2,
            ),
        }
        target_after = {
            **target_caps,
            "current_daily_tasks": target_caps["current_daily_tasks"] + transfer_tasks,
            "current_daily_hours": round(
                target_caps["current_daily_hours"] + transfer_hours,
                2,
            ),
        }

        await db.staffs.update_one(
            {"_id": overloaded_staff_id},
            {
                "$inc": {
                    "workload_caps.current_daily_tasks": -transfer_tasks,
                    "workload_caps.current_daily_hours": -transfer_hours,
                },
                "$set": {
                    "status": _status_for_caps(source_after, source.get("status")),
                },
            },
            session=session,
        )
        await db.staffs.update_one(
            {"_id": selected_staff_id},
            {
                "$inc": {
                    "workload_caps.current_daily_tasks": transfer_tasks,
                    "workload_caps.current_daily_hours": transfer_hours,
                },
                "$set": {
                    "status": _status_for_caps(target_after, target.get("status")),
                },
            },
            session=session,
        )

        log_id = await create_pending_overload_log(
            db,
            staff_id=overloaded_staff_id,
            trigger_reason=(
                f"Cân bằng tải lượng từ {overloaded_staff_id} "
                f"sang {selected_staff_id} theo gợi ý hệ thống"
            ),
            details={
                "source": "staff_workload_snapshot",
                "source_staff_id": overloaded_staff_id,
                "selected_staff_id": selected_staff_id,
                "department": source.get("department"),
                "transferred_daily_tasks": transfer_tasks,
                "transferred_daily_hours": transfer_hours,
                "source_before": source_caps,
                "source_after": source_after,
                "target_before": target_caps,
                "target_after": target_after,
            },
            session=session,
        )

        resolved_at = datetime.now(timezone.utc)
        await db.overload_logs.update_one(
            {"_id": log_id},
            {
                "$set": {
                    "manager_action.action_taken": (
                        ManagerActionTaken.APPROVED_SUGGESTION.value
                    ),
                    "manager_action.resolved_by": resolved_by,
                    "manager_action.details.resolved_at": resolved_at,
                    "manager_action.details.resolved_by": resolved_by,
                    "manager_action.details.action_taken": (
                        ManagerActionTaken.APPROVED_SUGGESTION.value
                    ),
                }
            },
            session=session,
        )

        return {
            "log_id": log_id,
            "action_taken": ManagerActionTaken.APPROVED_SUGGESTION.value,
            "resolved_by": resolved_by,
            "source_staff_id": overloaded_staff_id,
            "selected_staff_id": selected_staff_id,
            "transferred_daily_tasks": transfer_tasks,
            "transferred_daily_hours": transfer_hours,
            "source_after": source_after,
            "target_after": target_after,
        }

    async with await client.start_session() as session:
        return await session.with_transaction(_callback)


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

            target_department = (
                details.get("next_department")
                or details.get("department")
                or task.get("current_department")
            )
            if staff.get("department") != target_department:
                raise ValueError("STAFF_DEPARTMENT_MISMATCH")

            duration_hours = details.get("requested_duration_hours")
            if duration_hours is None:
                duration_hours = task.get("metrics", {}).get("step_duration_hours")
            if duration_hours is None:
                raise ValueError("INVALID_DURATION")
            duration_hours = float(duration_hours)
            if duration_hours <= 0:
                raise ValueError("INVALID_DURATION")

            previous_staff_id = task.get("current_assigned_to")
            if previous_staff_id == selected_staff_id:
                raise ValueError("STAFF_ALREADY_ASSIGNED")

            if staff.get("status") == "Nghỉ phép" or not _can_accept_projected_workload(
                staff,
                duration_hours,
            ):
                raise ValueError("STAFF_CAPACITY_EXCEEDED")

            if previous_staff_id:
                await db.staffs.update_one(
                    {"_id": previous_staff_id},
                    [
                        {
                            "$set": {
                                "workload_caps.current_daily_tasks": {
                                    "$max": [
                                        0,
                                        {
                                            "$subtract": [
                                                "$workload_caps.current_daily_tasks",
                                                1,
                                            ]
                                        },
                                    ]
                                },
                                "workload_caps.current_daily_hours": {
                                    "$max": [
                                        0.0,
                                        {
                                            "$subtract": [
                                                "$workload_caps.current_daily_hours",
                                                duration_hours,
                                            ]
                                        },
                                    ]
                                },
                            }
                        }
                    ],
                    session=session,
                )

            await db.staffs.update_one(
                {"_id": selected_staff_id},
                {
                    "$inc": {
                        "workload_caps.current_daily_tasks": 1,
                        "workload_caps.current_daily_hours": duration_hours,
                    }
                },
                session=session,
            )

            task_status = task.get("status")
            task_update: dict[str, Any] = {
                "current_assigned_to": selected_staff_id,
                "current_department": target_department,
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
                    {
                        "$set": {
                            "workflow_history.$.assigned_to": selected_staff_id,
                            "workflow_history.$.status": "Đang xử lý",
                        }
                    },
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
            "task_status": (
                "Đang xử lý"
                if task.get("status") in {"Tạm dừng", "Chờ xử lý"}
                and action_enum
                in {
                    ManagerActionTaken.APPROVED_SUGGESTION,
                    ManagerActionTaken.MANUAL_OVERRIDE,
                }
                else task.get("status")
            ),
            "updated_log": updated_log,
        }

    async with await client.start_session() as session:
        return await session.with_transaction(_callback)
