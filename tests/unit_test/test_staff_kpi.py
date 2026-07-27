import asyncio
from datetime import datetime, timedelta, timezone

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.dependencies import get_current_user
from app.api.v1 import analytics
from app.core.database import get_database
from app.core.roles import RoleEnum
from app.services.analytics_service import KPI_WINDOW_DAYS, list_staff_kpis


class FakeAggregationCursor:
    def __init__(self, items):
        self.items = items

    async def to_list(self, length):
        assert length is None
        return self.items


class FakeTasksCollection:
    def __init__(self, items):
        self.items = items
        self.pipeline = None
        self.options = None

    def aggregate(self, pipeline, **options):
        self.pipeline = pipeline
        self.options = options
        return FakeAggregationCursor(self.items)


class FakeDatabase:
    def __init__(self, items):
        self.tasks = FakeTasksCollection(items)


def test_list_staff_kpis_runs_the_calculation_in_mongodb() -> None:
    now = datetime(2026, 7, 27, 8, 0, tzinfo=timezone.utc)
    expected = [{"staff_id": "staff-a1", "efficiency_rate": 125.0}]
    db = FakeDatabase(expected)

    result = asyncio.run(list_staff_kpis(db, now=now))

    assert result == expected
    assert db.tasks.options == {"allowDiskUse": True}
    assert db.tasks.pipeline[0] == {
        "$match": {
            "status": "Hoàn thành",
            "timestamps.completed_at": {
                "$gte": now - timedelta(days=KPI_WINDOW_DAYS),
                "$lte": now,
            },
        }
    }

    group_stage = next(stage["$group"] for stage in db.tasks.pipeline if "$group" in stage)
    assert group_stage["_id"] == "$current_assigned_to"
    assert group_stage["total_tasks"] == {"$sum": 1}
    assert "total_actual_hours" in group_stage
    assert "reworked_tasks" in group_stage

    project_stage = next(
        stage["$project"] for stage in db.tasks.pipeline if "$project" in stage
    )
    assert "efficiency_rate" in project_stage
    assert "quality_score" in project_stage
    assert "total_rework_count" in project_stage


def _analytics_client(role: RoleEnum) -> tuple[TestClient, FakeDatabase]:
    app = FastAPI()
    db = FakeDatabase(
        [
            {
                "staff_id": "staff-a1",
                "staff_name": "Nguyễn Văn A",
                "department": "A",
                "total_tasks": 2,
                "total_standard_hours": 4.0,
                "total_actual_hours": 3.5,
                "efficiency_rate": 114.29,
                "reworked_tasks": 1,
                "total_rework_count": 1,
                "rework_rate": 50.0,
                "quality_score": 50.0,
            }
        ]
    )
    app.dependency_overrides[get_current_user] = lambda: {
        "sub": "test-user",
        "role": role,
    }
    app.dependency_overrides[get_database] = lambda: db
    app.include_router(analytics.router)
    return TestClient(app), db


def test_staff_kpi_endpoint_returns_precalculated_items_for_manager() -> None:
    client, _ = _analytics_client(RoleEnum.MANAGER)

    response = client.get("/api/v1/analytics/staff-kpi")

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["data"]["period_days"] == 30
    assert payload["data"]["items"][0]["staff_id"] == "staff-a1"


def test_staff_kpi_endpoint_rejects_staff_role() -> None:
    client, _ = _analytics_client(RoleEnum.STAFF)

    response = client.get("/api/v1/analytics/staff-kpi")

    assert response.status_code == 403
