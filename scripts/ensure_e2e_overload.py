from datetime import datetime, timedelta, timezone
import os

from dotenv import load_dotenv
from pymongo import MongoClient, UpdateOne


TASK_ID = "e2e_task_overload_pending"
LOG_ID = "e2e_log_overload_pending"
OVERLOADED_STAFF_ID = "e2e_staff_c_overloaded"
AVAILABLE_STAFF_ID = "e2e_staff_c_available"
BUSY_STAFF_ID = "e2e_staff_c_busy"


def main() -> None:
    load_dotenv()

    mongo_uri = os.environ.get("MONGO_URI", "mongodb://localhost:27017/?replicaSet=rs0")
    db_name = os.environ.get("MONGO_DB_NAME", "vnpt_ai_performance")
    now = datetime.now(timezone.utc)

    client = MongoClient(mongo_uri, serverSelectionTimeoutMS=5000)
    client.admin.command("ping")
    db = client[db_name]

    staff_docs = [
        {
            "_id": OVERLOADED_STAFF_ID,
            "fullname": "E2E Staff Overloaded",
            "department": "C",
            "workload_caps": {
                "max_daily_tasks": 5,
                "max_daily_hours": 8.0,
                "current_daily_tasks": 5,
                "current_daily_hours": 8.0,
            },
            "status": "Quá tải",
        },
        {
            "_id": AVAILABLE_STAFF_ID,
            "fullname": "E2E Staff Available",
            "department": "C",
            "workload_caps": {
                "max_daily_tasks": 5,
                "max_daily_hours": 8.0,
                "current_daily_tasks": 0,
                "current_daily_hours": 0.0,
            },
            "status": "Sẵn sàng",
        },
        {
            "_id": BUSY_STAFF_ID,
            "fullname": "E2E Staff Busy",
            "department": "C",
            "workload_caps": {
                "max_daily_tasks": 5,
                "max_daily_hours": 8.0,
                "current_daily_tasks": 3,
                "current_daily_hours": 4.0,
            },
            "status": "Bận",
        },
    ]

    db.staffs.bulk_write(
        [
            UpdateOne({"_id": staff["_id"]}, {"$set": staff}, upsert=True)
            for staff in staff_docs
        ]
    )

    task_doc = {
        "_id": TASK_ID,
        "task_code": "E2E-AI",
        "status": "Tạm dừng",
        "current_step": 1,
        "current_department": "C",
        "current_assigned_to": "",
        "metrics": {
            "workload_score": 4.0,
            "step_duration_hours": 0.5,
            "actual_duration_hours": None,
            "early_completion_hours": None,
            "remaining_step_hours": 0.5,
            "last_chunked_date": None,
        },
        "workflow_history": [
            {
                "step_number": 1,
                "department": "C",
                "assigned_to": "",
                "status": "Tạm dừng",
                "completed_at": None,
            }
        ],
        "control_flags": {"is_locked": False, "transfer_count": 0},
        "timestamps": {
            "created_at": now - timedelta(minutes=15),
            "due_at": now + timedelta(minutes=30),
            "completed_at": None,
        },
    }

    log_doc = {
        "_id": LOG_ID,
        "timestamp": now,
        "staff_id": OVERLOADED_STAFF_ID,
        "trigger_reason": "E2E fixture: pending overload requires manager approval",
        "manager_action": {
            "action_taken": "Pending",
            "resolved_by": "",
            "details": {
                "task_id": TASK_ID,
                "task_code": task_doc["task_code"],
                "current_step": task_doc["current_step"],
                "next_department": task_doc["current_department"],
                "requested_duration_hours": task_doc["metrics"]["step_duration_hours"],
            },
        },
    }

    db.tasks.update_one({"_id": TASK_ID}, {"$set": task_doc}, upsert=True)
    db.overload_logs.update_one({"_id": LOG_ID}, {"$set": log_doc}, upsert=True)

    client.close()
    print(f"Ensured E2E pending overload fixture: task={TASK_ID}, log={LOG_ID}")


if __name__ == "__main__":
    main()
