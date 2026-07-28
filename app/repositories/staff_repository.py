"""MongoDB queries for staff workload monitoring.

``staff.status`` exists in legacy documents, but it is not a reliable source for
the live workload state: counters are changed by task assignment/reset flows
without updating that field.  Every read used by the dashboards therefore
normalizes the counters and derives the workload status in MongoDB.
"""

from __future__ import annotations

from typing import Any, Optional

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.schemas.staff import Department

DEFAULT_MAX_DAILY_TASKS = 5
DEFAULT_MAX_DAILY_HOURS = 8.0


def _number_expression(path: str, target_type: str, default: int | float) -> dict[str, Any]:
    """Convert legacy numeric/string values without failing an aggregation."""
    return {
        "$max": [
            0,
            {
                "$convert": {
                    "input": path,
                    "to": target_type,
                    "onError": default,
                    "onNull": default,
                }
            },
        ]
    }


def staff_workload_normalization_stages() -> list[dict[str, Any]]:
    """Return reusable stages that normalize counters and derive live status."""
    return [
        {
            "$set": {
                "workload_caps": {
                    "max_daily_tasks": _number_expression(
                        "$workload_caps.max_daily_tasks",
                        "int",
                        DEFAULT_MAX_DAILY_TASKS,
                    ),
                    "max_daily_hours": _number_expression(
                        "$workload_caps.max_daily_hours",
                        "double",
                        DEFAULT_MAX_DAILY_HOURS,
                    ),
                    "current_daily_tasks": _number_expression(
                        "$workload_caps.current_daily_tasks",
                        "int",
                        0,
                    ),
                    "current_daily_hours": _number_expression(
                        "$workload_caps.current_daily_hours",
                        "double",
                        0.0,
                    ),
                }
            }
        },
        {
            "$set": {
                "status": {
                    "$switch": {
                        "branches": [
                            # Leave is an availability state and takes precedence.
                            {
                                "case": {"$eq": ["$status", "Nghỉ phép"]},
                                "then": "Nghỉ phép",
                            },
                            {
                                "case": {
                                    "$or": [
                                        {
                                            # Reaching the task-count cap means
                                            # "Bận" (cannot accept another task),
                                            # while exceeding it is anomalous
                                            # and must be surfaced as overload.
                                            "$gt": [
                                                "$workload_caps.current_daily_tasks",
                                                "$workload_caps.max_daily_tasks",
                                            ]
                                        },
                                        {
                                            "$gte": [
                                                "$workload_caps.current_daily_hours",
                                                "$workload_caps.max_daily_hours",
                                            ]
                                        },
                                    ]
                                },
                                "then": "Quá tải",
                            },
                            {
                                "case": {
                                    "$or": [
                                        {
                                            "$gt": [
                                                "$workload_caps.current_daily_tasks",
                                                0,
                                            ]
                                        },
                                        {
                                            "$gt": [
                                                "$workload_caps.current_daily_hours",
                                                0,
                                            ]
                                        },
                                    ]
                                },
                                "then": "Bận",
                            },
                        ],
                        "default": "Sẵn sàng",
                    }
                }
            }
        },
    ]


def build_staff_list_pipeline(
    departments: set[str] | None = None,
) -> list[dict[str, Any]]:
    """Build the canonical staff read pipeline used by both dashboards."""
    pipeline: list[dict[str, Any]] = []
    if departments:
        pipeline.append({"$match": {"department": {"$in": sorted(departments)}}})
    pipeline.extend(staff_workload_normalization_stages())
    pipeline.append({"$sort": {"department": 1, "fullname": 1}})
    return pipeline


async def get_staffs(
    db: AsyncIOMotorDatabase,
    *,
    departments: set[str] | None = None,
) -> list[dict[str, Any]]:
    """Return staff with defensive numeric fields and a live workload status."""
    return await db.staffs.aggregate(
        build_staff_list_pipeline(departments)
    ).to_list(length=None)


async def get_dashboard_summary(
    db: AsyncIOMotorDatabase,
    department: Optional[Department] = None,
) -> list[dict[str, Any]]:
    """Aggregate department totals from the same normalized staff snapshot."""
    departments = {department} if department else None
    pipeline = build_staff_list_pipeline(departments)

    # The staff-list sort is irrelevant before grouping.
    pipeline.pop()
    pipeline.extend(
        [
            {
                "$group": {
                    "_id": "$department",
                    "total_tasks": {"$sum": "$workload_caps.current_daily_tasks"},
                    "total_hours": {"$sum": "$workload_caps.current_daily_hours"},
                    "staff_count": {"$sum": 1},
                    "avg_hours": {"$avg": "$workload_caps.current_daily_hours"},
                    "statuses": {"$push": "$status"},
                }
            },
            {
                "$set": {
                    "by_status": {
                        "$map": {
                            "input": {"$setUnion": [[], "$statuses"]},
                            "as": "status",
                            "in": {
                                "status": "$$status",
                                "count": {
                                    "$size": {
                                        "$filter": {
                                            "input": "$statuses",
                                            "as": "candidate_status",
                                            "cond": {
                                                "$eq": [
                                                    "$$candidate_status",
                                                    "$$status",
                                                ]
                                            },
                                        }
                                    }
                                },
                            },
                        }
                    }
                }
            },
            {"$project": {"statuses": 0}},
            {"$sort": {"_id": 1}},
        ]
    )
    return await db.staffs.aggregate(pipeline).to_list(length=None)
