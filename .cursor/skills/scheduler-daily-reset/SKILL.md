---
name: scheduler-daily-reset
description: >-
  Implements daily workload reset cron at 00:00 Asia/Ho_Chi_Minh with APScheduler
  and idempotent chunking. Use when implementing daily-reset endpoint, daily_reset_job,
  APScheduler, workload chunking, or remaining_step_hours / last_chunked_date fields.
---

# Daily Reset Cron (00:00 VN) — APScheduler

Target: `POST /api/v1/system/daily-reset` + scheduler registration in app lifespan (`app/cron/daily_reset_job.py`).

Spec details: `.cursor/rules/03-sau-api-cot-loi.mdc` §6, [build-six-core-apis](../build-six-core-apis/SKILL.md) Phase 3.

## Timezone — mandatory

`CronTrigger(hour=0, minute=0)` without timezone uses server default (often UTC → 07:00 VN).

```python
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from zoneinfo import ZoneInfo

scheduler = AsyncIOScheduler(timezone=ZoneInfo("Asia/Ho_Chi_Minh"))

scheduler.add_job(
    execute_daily_workload_chunking_trigger,
    CronTrigger(hour=0, minute=0, timezone=ZoneInfo("Asia/Ho_Chi_Minh")),
    args=[db],
    id="daily_reset_job",
    replace_existing=True,
    misfire_grace_time=3600,
)
```

## Multi-worker duplicate runs

`uvicorn --workers 4` → 4 schedulers → 4 resets at midnight.

| Strategy | When |
|----------|------|
| Single scheduler process (recommended MVP) | `--workers 1` or dedicated cron container |
| MongoDB distributed lock (`_scheduler_locks`) | Horizontal scale required |

## Idempotent chunking

Reset `current_daily_tasks=0, current_daily_hours=0.0` is naturally idempotent.

Chunking must skip tasks already processed today via `last_chunked_date`:

```python
async def execute_daily_workload_chunking_trigger(db):
    from datetime import datetime
    from zoneinfo import ZoneInfo

    today_vn = datetime.now(ZoneInfo("Asia/Ho_Chi_Minh")).date().isoformat()

    await db.staffs.update_many(
        {}, {"$set": {"workload_caps.current_daily_tasks": 0,
                       "workload_caps.current_daily_hours": 0.0}}
    )

    async for task in db.tasks.find({"status": "Đang xử lý"}):
        if task.get("metrics", {}).get("last_chunked_date") == today_vn:
            continue
        remaining = task["metrics"].get("remaining_step_hours", task["metrics"]["step_duration_hours"])
        chunked_hours = min(remaining, 4.0)
        staff_id = task["current_assigned_to"]

        await db.staffs.update_one(
            {"_id": staff_id},
            {"$inc": {"workload_caps.current_daily_hours": chunked_hours}}
        )
        await db.tasks.update_one(
            {"_id": task["_id"]},
            {"$set": {"metrics.remaining_step_hours": max(remaining - chunked_hours, 0.0),
                      "metrics.last_chunked_date": today_vn}}
        )
```

Use `remaining_step_hours` (not raw `step_duration_hours`) to avoid double-counting across consecutive resets.

## Auth

Endpoint for manual/CI only — protect with `X-Internal-Secret` header (`07-authentication-authorization.mdc`). Prefer calling the function directly from APScheduler, not HTTP self-call.

## Done when

- [ ] Runs at 00:00 `Asia/Ho_Chi_Minh`
- [ ] Re-run same day does not inflate workload
- [ ] Multi-worker duplicate strategy documented or implemented
