import asyncio
import unittest

from app.repositories.staff_repository import build_staff_list_pipeline
from app.services.analytics_service import (
    apply_capacity_suggestion,
    build_staff_suggestions,
    calculate_capacity_transfer,
    list_pending_overloads,
)


class _FakeCursor:
    def __init__(self, items):
        self.items = items

    def sort(self, *args, **kwargs):
        return self

    async def to_list(self, length):
        return self.items


class _FakeCollection:
    def __init__(self, *, find_items=None, aggregate_items=None):
        self.find_items = find_items or []
        self.aggregate_items = aggregate_items or []

    def find(self, *args, **kwargs):
        return _FakeCursor(self.find_items)

    def aggregate(self, *args, **kwargs):
        return _FakeCursor(self.aggregate_items)


class _FakeDatabase:
    def __init__(self, staffs, logs=None, tasks=None):
        self.staffs = _FakeCollection(aggregate_items=staffs)
        self.overload_logs = _FakeCollection(find_items=logs)
        self.tasks = _FakeCollection(find_items=tasks)


def _set_dotted(document, path, value):
    target = document
    parts = path.split(".")
    for part in parts[:-1]:
        target = target.setdefault(part, {})
    target[parts[-1]] = value


def _get_dotted(document, path):
    target = document
    for part in path.split("."):
        target = target[part]
    return target


class _MutableCollection:
    def __init__(self, documents=None):
        self.documents = {item["_id"]: item for item in (documents or [])}

    async def find_one(self, query, **kwargs):
        return self.documents.get(query.get("_id"))

    async def count_documents(self, query, **kwargs):
        return len(self.documents)

    async def insert_one(self, document, **kwargs):
        self.documents[document["_id"]] = document

    async def update_one(self, query, update, **kwargs):
        document = self.documents[query["_id"]]
        for path, amount in update.get("$inc", {}).items():
            _set_dotted(document, path, _get_dotted(document, path) + amount)
        for path, value in update.get("$set", {}).items():
            _set_dotted(document, path, value)


class _FakeSession:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return False

    async def with_transaction(self, callback):
        return await callback(self)


class _FakeClient:
    async def start_session(self):
        return _FakeSession()


class _MutableDatabase:
    def __init__(self, staffs):
        self.staffs = _MutableCollection(staffs)
        self.overload_logs = _MutableCollection()


class AnalyticsServiceTests(unittest.TestCase):
    def test_staff_pipeline_normalizes_numbers_and_derives_status(self):
        pipeline = build_staff_list_pipeline()

        caps_stage = pipeline[0]["$set"]["workload_caps"]
        self.assertEqual(
            caps_stage["current_daily_hours"]["$max"][1]["$convert"]["to"],
            "double",
        )

        branches = pipeline[1]["$set"]["status"]["$switch"]["branches"]
        overload_condition = branches[1]["case"]["$or"]
        # At the task-count cap alone the staff is Busy; only exceeding that
        # cap or reaching the hours cap is considered a live overload alert.
        self.assertIn("$gt", overload_condition[0])
        self.assertIn("$gte", overload_condition[1])

    def test_build_staff_suggestions_ranks_less_loaded_staff_first(self):
        candidates = [
            {
                "_id": "staff_a",
                "department": "A",
                "status": "Sẵn sàng",
                "workload_caps": {
                    "current_daily_tasks": 2,
                    "current_daily_hours": 4.0,
                    "max_daily_tasks": 5,
                    "max_daily_hours": 8.0,
                },
            },
            {
                "_id": "staff_b",
                "department": "A",
                "status": "Sẵn sàng",
                "workload_caps": {
                    "current_daily_tasks": 1,
                    "current_daily_hours": 2.0,
                    "max_daily_tasks": 5,
                    "max_daily_hours": 8.0,
                },
            },
            {
                "_id": "staff_c",
                "department": "A",
                "status": "Nghỉ phép",
                "workload_caps": {
                    "current_daily_tasks": 0,
                    "current_daily_hours": 0.0,
                    "max_daily_tasks": 5,
                    "max_daily_hours": 8.0,
                },
            },
        ]

        suggestions = build_staff_suggestions(candidates, duration_hours=1.0)

        self.assertEqual([s["staff_id"] for s in suggestions], ["staff_b", "staff_a"])
        self.assertAlmostEqual(suggestions[0]["matching_score"], 0.75)
        self.assertAlmostEqual(suggestions[1]["matching_score"], 0.5)

    def test_capacity_transfer_uses_one_average_task_unit(self):
        transfer = calculate_capacity_transfer(
            {
                "workload_caps": {
                    "current_daily_tasks": 5,
                    "current_daily_hours": 8.0,
                    "max_daily_tasks": 5,
                    "max_daily_hours": 8.0,
                }
            }
        )

        self.assertEqual(transfer, {"daily_tasks": 1, "daily_hours": 1.6})

    def test_capacity_suggestion_does_not_move_overload_to_target(self):
        candidates = [
            {
                "_id": "would_reach_hours_cap",
                "status": "Bận",
                "workload_caps": {
                    "current_daily_tasks": 2,
                    "current_daily_hours": 6.4,
                    "max_daily_tasks": 5,
                    "max_daily_hours": 8.0,
                },
            }
        ]

        suggestions = build_staff_suggestions(
            candidates,
            1.6,
            keep_below_hours_cap=True,
        )

        self.assertEqual(suggestions, [])

    def test_live_capacity_alert_is_returned_without_pending_log(self):
        staffs = [
            {
                "_id": "staff_overloaded",
                "fullname": "Nhân sự quá tải",
                "department": "A",
                "status": "Quá tải",
                "workload_caps": {
                    "current_daily_tasks": 5,
                    "current_daily_hours": 8.0,
                    "max_daily_tasks": 5,
                    "max_daily_hours": 8.0,
                },
            },
            {
                "_id": "staff_available",
                "fullname": "Nhân sự sẵn sàng",
                "department": "A",
                "status": "Bận",
                "workload_caps": {
                    "current_daily_tasks": 1,
                    "current_daily_hours": 2.0,
                    "max_daily_tasks": 5,
                    "max_daily_hours": 8.0,
                },
            },
        ]
        db = _FakeDatabase(staffs)

        alerts = asyncio.run(list_pending_overloads(db))

        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0]["_id"], "capacity:staff_overloaded")
        self.assertEqual(alerts[0]["alert_type"], "staff_capacity")
        self.assertTrue(alerts[0]["resolvable"])
        self.assertEqual(
            alerts[0]["suggested_transfer"],
            {"daily_tasks": 1, "daily_hours": 1.6},
        )
        self.assertEqual(
            [item["staff_id"] for item in alerts[0]["suggestions"]],
            ["staff_available"],
        )

    def test_apply_capacity_suggestion_updates_both_staffs_and_audit_log(self):
        source = {
            "_id": "staff_overloaded",
            "department": "A",
            "status": "Quá tải",
            "workload_caps": {
                "current_daily_tasks": 5,
                "current_daily_hours": 8.0,
                "max_daily_tasks": 5,
                "max_daily_hours": 8.0,
            },
        }
        target = {
            "_id": "staff_available",
            "department": "A",
            "status": "Bận",
            "workload_caps": {
                "current_daily_tasks": 1,
                "current_daily_hours": 2.0,
                "max_daily_tasks": 5,
                "max_daily_hours": 8.0,
            },
        }
        db = _MutableDatabase([source, target])

        result = asyncio.run(
            apply_capacity_suggestion(
                db,
                _FakeClient(),
                "staff_overloaded",
                selected_staff_id="staff_available",
                resolved_by="manager_01",
            )
        )

        self.assertEqual(source["workload_caps"]["current_daily_tasks"], 4)
        self.assertEqual(source["workload_caps"]["current_daily_hours"], 6.4)
        self.assertEqual(source["status"], "Bận")
        self.assertEqual(target["workload_caps"]["current_daily_tasks"], 2)
        self.assertEqual(target["workload_caps"]["current_daily_hours"], 3.6)
        self.assertEqual(result["transferred_daily_hours"], 1.6)

        log = db.overload_logs.documents[result["log_id"]]
        self.assertEqual(
            log["manager_action"]["action_taken"],
            "Approved_Suggestion",
        )
        self.assertEqual(log["manager_action"]["resolved_by"], "manager_01")


if __name__ == "__main__":
    unittest.main()
