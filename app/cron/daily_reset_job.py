import logging

from datetime import datetime, timezone
from typing import Any

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from pymongo import UpdateOne

logger = logging.getLogger(__name__)

CHUNK_MAX_HOURS = 4.0

# Đây là "khóa" idempotency cho cronjob, tách riêng khỏi collection tasks
# để tránh race condition (2 lệnh gọi job gần như đồng thời) và tránh
# trường hợp job bị coi là "chưa chạy" khi mọi task active đều bị skip.
# Collection này không có $jsonSchema validator, có thể tạo tự do.
RESET_STATE_COLLECTION = "system_state"
RESET_STATE_ID = "daily_reset"


def build_chunking_update_for_task(task: dict[str, Any], today_str: str) -> dict[str, Any] | None:
    """Build a chunking update for a single task with idempotency protection."""

    if task.get("status") != "Đang xử lý":
        return None

    # Task đang bị khóa (ví dụ đang review/tranh chấp) thì không tự động
    # trừ giờ hay tính lại workload trong lúc reset.
    control_flags = task.get("control_flags") or {}
    if control_flags.get("is_locked"):
        return None

    assigned_to = task.get("current_assigned_to") or ""
    if not assigned_to:
        return None

    metrics = task.get("metrics") or {}
    if metrics.get("last_chunked_date") == today_str:
        return None

    remaining_hours = metrics.get("remaining_step_hours")
    if remaining_hours is None:
        remaining_hours = metrics.get("step_duration_hours")
    if remaining_hours is None:
        return None

    remaining_hours = float(remaining_hours)
    if remaining_hours <= 0:
        return None

    # Làm tròn một lần duy nhất và dùng chung giá trị này cho cả
    # task.metrics.remaining_step_hours và staff.workload_caps.current_daily_hours,
    # tránh lệch số liệu tích lũy giữa hai collection qua nhiều ngày.
    chunked_hours = round(min(remaining_hours, CHUNK_MAX_HOURS), 2)
    updated_remaining = round(max(remaining_hours - chunked_hours, 0.0), 2)

    return {
        "task_update": {
            "metrics.remaining_step_hours": updated_remaining,
            "metrics.last_chunked_date": today_str,
        },
        "staff_inc": {
            "workload_caps.current_daily_tasks": 1,
            "workload_caps.current_daily_hours": chunked_hours,
        },
    }


async def _acquire_daily_reset_lock(db: AsyncIOMotorDatabase, session, today_str: str) -> bool:
    """
    Đảm bảo job chỉ thực sự chạy (reset + chunk) một lần cho mỗi ngày,
    bất kể có task nào bị skip trong build_chunking_update_for_task hay không,
    và bất kể có 2 lệnh gọi job trùng thời điểm.

    Trả về True nếu lock được giữ (job được phép chạy tiếp), False nếu đã chạy rồi.
    Toàn bộ được thực hiện trong transaction, nên nếu có race condition thật,
    MongoDB sẽ tự phát hiện write conflict và session.with_transaction sẽ retry.
    """
    existing = await db[RESET_STATE_COLLECTION].find_one(
        {"_id": RESET_STATE_ID},
        session=session,
    )
    if existing and existing.get("last_run_date") == today_str:
        return False

    # Tại điểm này, existing không tồn tại HOẶC last_run_date != today_str,
    # nên filter dưới đây luôn khớp (hoặc không khớp document nào -> upsert insert mới),
    # không có rủi ro duplicate key trên _id.
    await db[RESET_STATE_COLLECTION].update_one(
        {"_id": RESET_STATE_ID, "last_run_date": {"$ne": today_str}},
        {
            "$set": {
                "last_run_date": today_str,
                "last_run_at": datetime.now(timezone.utc),
            }
        },
        upsert=True,
        session=session,
    )
    return True


async def run_daily_reset(
    db: AsyncIOMotorDatabase,
    client: AsyncIOMotorClient,
) -> dict[str, Any]:
    """Reset workload counters and chunk active tasks in one MongoDB transaction."""

    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    async def _callback(session) -> dict[str, Any]:
        lock_acquired = await _acquire_daily_reset_lock(db, session, today_str)
        if not lock_acquired:
            return {
                "status": "skipped",
                "message": f"Cronjob đã chạy trong ngày {today_str}, bỏ qua để bảo toàn dữ liệu.",
            }

        reset_result = await db.staffs.update_many(
            {},
            {
                "$set": {
                    "workload_caps.current_daily_tasks": 0,
                    "workload_caps.current_daily_hours": 0.0,
                }
            },
            session=session,
        )

        active_tasks = await db.tasks.find(
            {"status": "Đang xử lý"},
            session=session,
        ).to_list(length=None)

        task_ops: list[UpdateOne] = []
        staff_totals: dict[str, dict[str, Any]] = {}
        skipped_tasks = 0
        chunked_tasks = 0

        for task in active_tasks:
            update = build_chunking_update_for_task(task, today_str)
            if update is None:
                skipped_tasks += 1
                continue

            task_ops.append(
                UpdateOne({"_id": task["_id"]}, {"$set": update["task_update"]})
            )
            chunked_tasks += 1

            staff_id = task.get("current_assigned_to") or ""
            if not staff_id:
                continue

            payload = staff_totals.setdefault(
                staff_id,
                {"tasks": 0, "hours": 0.0},
            )
            payload["tasks"] += 1
            payload["hours"] += float(update["staff_inc"]["workload_caps.current_daily_hours"])

        if task_ops:
            await db.tasks.bulk_write(task_ops, session=session)

        if staff_totals:
            staff_ops = [
                UpdateOne(
                    {"_id": staff_id},
                    {
                        "$inc": {
                            "workload_caps.current_daily_tasks": payload["tasks"],
                            "workload_caps.current_daily_hours": round(payload["hours"], 2),
                        }
                    },
                )
                for staff_id, payload in staff_totals.items()
            ]
            await db.staffs.bulk_write(staff_ops, session=session)

        logger.info(
            "Daily reset completed: matched_staffs=%s modified_staffs=%s "
            "chunked_tasks=%s skipped_tasks=%s",
            reset_result.matched_count,
            reset_result.modified_count,
            chunked_tasks,
            skipped_tasks,
        )

        return {
            "status": "completed",
            "triggered_at": datetime.now(timezone.utc).isoformat(),
            "matched_staffs": int(reset_result.matched_count),
            "reset_staffs": int(reset_result.modified_count),
            "chunked_tasks": chunked_tasks,
            "skipped_tasks": skipped_tasks,
            "staff_ids_updated": sorted(staff_totals.keys()),
        }

    async with await client.start_session() as session:
        return await session.with_transaction(_callback)