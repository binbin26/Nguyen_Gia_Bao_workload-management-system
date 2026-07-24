from datetime import datetime, timedelta, timezone
import os

from dotenv import load_dotenv
from pymongo import MongoClient, UpdateOne


CATEGORY_ID = "e2e_category_task_control"
TASK_CODE = "E2E-TASK"
TASK_ID = "e2e_task_control_processing"
STAFF_A_ID = "e2e_staff_task_a"
STAFF_B_ID = "e2e_staff_task_b"


def main() -> None:
    load_dotenv()

    mongo_uri = os.environ.get("MONGO_URI", "mongodb://localhost:27017/?replicaSet=rs0")
    db_name = os.environ.get("MONGO_DB_NAME", "vnpt_ai_performance")
    now = datetime.now(timezone.utc)

    client = MongoClient(mongo_uri, serverSelectionTimeoutMS=5000)
    client.admin.command("ping")
    db = client[db_name]

    category_doc = {
        "_id": CATEGORY_ID,
        "task_code": TASK_CODE,
        "title": "E2E Task Control Center workflow",
        "department": "A",
        "standard_metrics": {
            "total_steps": 2,
            "total_duration_hours": 0.5,
            "complexity": 1,
            "urgency": 1,
            "coordination": 1,
            "workload_score": 1.0,
        },
        "workflow_steps": [
            {
                "step_number": 1,
                "department": "A",
                "duration_hours": 0.25,
                "desc": "E2E current processing step",
            },
            {
                "step_number": 2,
                "department": "B",
                "duration_hours": 0.25,
                "desc": "E2E next processing step",
            },
        ],
    }

    staff_docs = [
        {
            "_id": STAFF_A_ID,
            "fullname": "E2E Task Staff A",
            "department": "A",
            "workload_caps": {
                "max_daily_tasks": 5,
                "max_daily_hours": 8.0,
                "current_daily_tasks": 1,
                "current_daily_hours": 0.25,
            },
            "status": "Sẵn sàng",
        },
        {
            "_id": STAFF_B_ID,
            "fullname": "E2E Task Staff B",
            "department": "B",
            "workload_caps": {
                "max_daily_tasks": 5,
                "max_daily_hours": 8.0,
                "current_daily_tasks": 0,
                "current_daily_hours": 0.0,
            },
            "status": "Sẵn sàng",
        },
    ]

    task_doc = {
        "_id": TASK_ID,
        "task_code": TASK_CODE,
        "status": "Đang xử lý",
        "current_step": 1,
        "current_department": "A",
        "current_assigned_to": STAFF_A_ID,
        "metrics": {
            "workload_score": 1.0,
            "step_duration_hours": 0.25,
            "actual_duration_hours": None,
            "early_completion_hours": None,
            "remaining_step_hours": 0.25,
            "last_chunked_date": None,
        },
        "workflow_history": [
            {
                "step_number": 1,
                "department": "A",
                "assigned_to": STAFF_A_ID,
                "status": "Đang xử lý",
                "completed_at": None,
            }
        ],
        "control_flags": {"is_locked": False, "transfer_count": 0},
        "timestamps": {
            "created_at": now - timedelta(minutes=10),
            "due_at": now + timedelta(minutes=15),
            "completed_at": None,
        },
    }

    db.task_categories.update_one(
        {"_id": CATEGORY_ID},
        {"$set": category_doc},
        upsert=True,
    )
    db.staffs.bulk_write(
        [
            UpdateOne({"_id": staff["_id"]}, {"$set": staff}, upsert=True)
            for staff in staff_docs
        ]
    )
    db.tasks.update_one({"_id": TASK_ID}, {"$set": task_doc}, upsert=True)

    client.close()
    print(f"Ensured E2E Task Control fixture: task={TASK_ID}, code={TASK_CODE}")


if __name__ == "__main__":
    main()
