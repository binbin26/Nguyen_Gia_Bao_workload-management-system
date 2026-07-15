import unittest

from app.services.analytics_service import build_staff_suggestions


class AnalyticsServiceTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
