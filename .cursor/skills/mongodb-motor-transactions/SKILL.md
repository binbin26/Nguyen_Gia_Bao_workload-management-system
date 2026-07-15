---
name: mongodb-motor-transactions
description: >-
  Implements MongoDB ACID transactions with Motor async driver for multi-collection
  writes. Use when implementing next-step, resolve-overload, or any code using
  start_session, with_transaction, or session=session with Motor.
---

# MongoDB ACID Transactions (Motor)

Required for: `POST /tasks/{id}/next-step`, `POST /analytics/resolve-overload`.

## Prerequisite: replica set

Standalone `mongod` raises `OperationFailure: Transaction numbers are only allowed on a replica set member or mongos`.

```bash
mongod --replSet rs0 --dbpath ./data
# mongosh:
rs.initiate()
```

## Pattern: `with_transaction` (auto-retry)

Do **not** manually `start_transaction()` / `commit_transaction()`. Motor retries `TransientTransactionError` and `UnknownTransactionCommitResult`.

```python
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

async def process_next_step(task_id: str, actual_duration: float,
                             client: AsyncIOMotorClient, db: AsyncIOMotorDatabase):

    async def _callback(session):
        task = await db.tasks.find_one({"_id": task_id}, session=session)
        if not task:
            raise ValueError("TASK_NOT_FOUND")
        if task["status"] in ("Hoàn thành", "Hủy"):
            raise ValueError("TASK_ALREADY_CLOSED")

        # All reads/writes on tasks, staffs, overload_logs — pass session=session

        return {"status": "success"}

    async with await client.start_session() as session:
        result = await session.with_transaction(_callback)
        return result
```

## Common mistakes

| Mistake | Consequence |
|---------|-------------|
| Omit `session=session` on any Motor call | That op runs outside txn → partial commit on failure |
| Raise generic `Exception` for business errors | Router can't map to 404/409; retry behavior unclear |
| Heavy work inside txn (HTTP, PuLP batch) | Timeout / lock contention — compute **before** txn, pass `staff_id` in |
| Reuse session across requests | Not safe for concurrent requests |

Map business exceptions to HTTP at router layer; let transient errors retry via `with_transaction`.

## Done when

- [ ] Multi-collection writes in one transaction
- [ ] Every Motor call inside callback passes `session=session`
- [ ] Business errors → correct HTTP status without orphan writes
