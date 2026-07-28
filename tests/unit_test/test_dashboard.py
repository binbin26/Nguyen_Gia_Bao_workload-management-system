"""
Test script để xác minh dashboard aggregation logic.
Chạy sau khi seed database.
"""

import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from app.core.config import settings
from app.repositories.staff_repository import get_dashboard_summary


async def _run_dashboard_aggregation():
    """Test aggregation pipeline trên dữ liệu thực."""
    # Kết nối tới MongoDB
    client = AsyncIOMotorClient(
        settings.MONGO_URI,
        replicaSet=settings.MONGO_REPLICA_SET,
    )
    db = client[settings.MONGO_DB_NAME]

    try:
        # Test 1: Get summary for all departments
        print("=== Test 1: All departments ===")
        result = await get_dashboard_summary(db, department=None)
        for dept in result:
            print(f"Department {dept['_id']}:")
            print(f"  Total tasks: {dept['total_tasks']}")
            print(f"  Total hours: {dept['total_hours']}")
            print(f"  Staff count: {dept['staff_count']}")
            print(f"  Avg hours: {dept['avg_hours']:.2f}")
            print(f"  By status: {dept['by_status']}")
            print()

        # Test 2: Get summary for department B only
        print("=== Test 2: Department B only ===")
        result = await get_dashboard_summary(db, department="B")
        if result:
            dept = result[0]
            print(f"Department {dept['_id']}:")
            print(f"  Total tasks: {dept['total_tasks']}")
            print(f"  Total hours: {dept['total_hours']}")
            print(f"  Staff count: {dept['staff_count']}")
            print(f"  Avg hours: {dept['avg_hours']:.2f}")
            print(f"  By status: {dept['by_status']}")
        else:
            print("No data for department B")

    finally:
        client.close()


def test_dashboard_aggregation():
    """Run the async MongoDB integration check without a pytest async plugin."""
    asyncio.run(_run_dashboard_aggregation())

if __name__ == "__main__":
    test_dashboard_aggregation()
