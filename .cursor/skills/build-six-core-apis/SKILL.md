---
name: build-six-core-apis
description: >-
  Guides phased implementation of the 6 core Workforce Management APIs
  (tasks, next-step, dashboard, overloads, resolve-overload, daily-reset).
  Use when building the project from scratch, implementing one API at a time,
  or when the user asks to follow the 6-API roadmap step by step.
---

# Build 6 Core APIs — Phased Roadmap

Read `.cursor/rules/03-sau-api-cot-loi.mdc` before implementing any endpoint. Cross-reference specialized skills as each phase requires them.

| Phase | Skill to load |
|-------|---------------|
| Transaction APIs | [mongodb-motor-transactions](../mongodb-motor-transactions/SKILL.md) |
| Daily reset + cron | [scheduler-daily-reset](../scheduler-daily-reset/SKILL.md) |
| PuLP / ai_suggestions (Phase 4) | [pulp-staff-assignment](../pulp-staff-assignment/SKILL.md) |

## Phase 0 — Foundation

1. Run `scripts/seed_workforce_db.py` (MongoDB **must** be replica set — see mongodb-motor-transactions skill).
2. Write Pydantic models for 4 collections per `01-mongodb-schema-du-lieu.mdc` (`_id: str` alias).
3. Implement `dependencies.py`: `verify_workload_capacity()` — projection check: `(current + new) <= max` for both tasks and hours (`03-sau-api-cot-loi.mdc` §1 step 5).

## Phase 1 — Simple APIs (no transaction)

4. `GET /api/v1/dashboard/summary` — read-only aggregation; verifies DB + pipeline.
5. `POST /api/v1/tasks` — happy path with greedy `pick_best_staff` (pulp-staff-assignment skill, Step 1).
6. Unit tests for step 5 per `06-testing-checklist.mdc` **before** continuing.

## Phase 2 — Transaction-heavy APIs

7. `POST /api/v1/tasks/{id}/next-step` — mongodb-motor-transactions pattern; handle final step, next-step, and "no staff in next dept" → `Tạm dừng` + overload log.
8. `GET /api/v1/analytics/overloads` + `POST /api/v1/analytics/resolve-overload` — fix `"Pending"` enum in schema first (`01-mongodb-schema-du-lieu.mdc`).

## Phase 3 — Automation & ops

9. `POST /api/v1/system/daily-reset` + APScheduler in app lifespan — scheduler-daily-reset skill (VN timezone, dedup, idempotent chunking).
10. E2E integration test: create task → next-step → daily-reset → verify dashboard numbers.

## Phase 4 — Optional upgrades (post-MVP)

11. Replace greedy picker with PuLP `solve_batch_assignment` for `ai_suggestions` — pulp-staff-assignment skill Steps 2–3.
12. Capability matrix (long-term Phase 3) — design new collection before coding.

## Agent usage

Request one phase at a time, e.g. *"Read build-six-core-apis and implement Phase 1"* — avoids coding all 6 APIs in parallel.

## Done when

- [ ] Built in phase order; tests between phases not skipped
- [ ] Simple APIs before transaction APIs
- [ ] Full flow task → next-step → daily-reset verified
