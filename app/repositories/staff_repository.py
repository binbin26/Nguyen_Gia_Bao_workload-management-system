"""
Staff repository — MongoDB Motor operations on staffs collection.

Per 03-sau-api-cot-loi.mdc §3 (Dashboard Summary):
Dùng MongoDB Aggregation Pipeline thay vì loop Python để tổng hợp dữ liệu,
không bao giờ dùng vòng lặp Python để cộng dồn thủ công.
"""

from motor.motor_asyncio import AsyncIOMotorDatabase
from typing import Optional

from app.schemas.staff import Department


async def get_staffs(db: AsyncIOMotorDatabase) -> list[dict]:
    """
    Retrieve all staff documents for manager workload monitoring.

    Sorted by department then fullname so the dashboard renders consistently.
    """
    return await db.staffs.find({}).sort(
        [("department", 1), ("fullname", 1)]
    ).to_list(None)


async def get_dashboard_summary(
    db: AsyncIOMotorDatabase,
    department: Optional[Department] = None,
) -> dict:
    """
    Retrieve real-time workload summary per department using MongoDB aggregation.

    Uses $match (optional by dept) → $group to compute:
    - Total current_daily_tasks across all staff in dept
    - Total current_daily_hours across all staff in dept
    - Number of staff by status
    - Average ETC (current_daily_hours mean)

    Args:
        db: Motor async database
        department: Filter by dept (A, B, or C), or None for all depts

    Returns:
        List of aggregated documents, one per department (or one if dept specified).
        Example:
        [
            {
                "_id": "A",
                "total_tasks": 10,
                "total_hours": 25.5,
                "staff_count": 4,
                "avg_hours": 6.375,
                "by_status": [
                    {"status": "Sẵn sàng", "count": 2},
                    {"status": "Bận", "count": 1},
                    ...
                ]
            }
        ]
    """
    pipeline = []

    # Step 1: Filter by department if specified
    if department:
        pipeline.append({"$match": {"department": department}})

    # Step 2: Group by department, compute totals and stats
    pipeline.append(
        {
            "$group": {
                "_id": "$department",
                "total_tasks": {
                    "$sum": "$workload_caps.current_daily_tasks"
                },
                "total_hours": {
                    "$sum": "$workload_caps.current_daily_hours"
                },
                "staff_count": {"$sum": 1},
                "avg_hours": {
                    "$avg": "$workload_caps.current_daily_hours"
                },
                "statuses": {"$push": "$status"},
            }
        }
    )

    # Step 3: Compute status breakdown
    pipeline.append(
        {
            "$addFields": {
                "by_status": {
                    "$map": {
                        "input": {
                            "$setUnion": [
                                [],
                                "$statuses",
                            ]  # Get unique statuses
                        },
                        "as": "status",
                        "in": {
                            "status": "$$status",
                            "count": {
                                "$size": {
                                    "$filter": {
                                        "input": "$statuses",
                                        "as": "s",
                                        "cond": {
                                            "$eq": ["$$s", "$$status"]
                                        },
                                    }
                                }
                            },
                        },
                    }
                }
            }
        }
    )

    # Step 4: Clean up intermediate field
    pipeline.append({"$project": {"statuses": 0}})

    # Step 5: Sort by department for consistency
    pipeline.append({"$sort": {"_id": 1}})

    result = await db.staffs.aggregate(pipeline).to_list(None)
    return result
