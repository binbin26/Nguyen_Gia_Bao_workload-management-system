from app.cron.daily_reset_job import build_chunking_update_for_task


def test_build_chunking_update_skips_already_chunked_task() -> None:
    task = {
        "_id": "task-1",
        "status": "Đang xử lý",
        "current_assigned_to": "staff-1",
        "metrics": {
            "remaining_step_hours": 3.5,
            "step_duration_hours": 3.5,
            "last_chunked_date": "2026-07-15",
        },
    }

    assert build_chunking_update_for_task(task, "2026-07-15") is None


def test_build_chunking_update_uses_remaining_hours_and_caps_staff() -> None:
    task = {
        "_id": "task-2",
        "status": "Đang xử lý",
        "current_assigned_to": "staff-2",
        "metrics": {
            "remaining_step_hours": 6.5,
            "step_duration_hours": 6.5,
            "last_chunked_date": None,
        },
    }

    update = build_chunking_update_for_task(task, "2026-07-15")

    assert update is not None
    assert update["task_update"]["metrics.remaining_step_hours"] == 2.5
    assert update["task_update"]["metrics.last_chunked_date"] == "2026-07-15"
    assert update["staff_inc"]["workload_caps.current_daily_tasks"] == 1
    assert update["staff_inc"]["workload_caps.current_daily_hours"] == 4.0
