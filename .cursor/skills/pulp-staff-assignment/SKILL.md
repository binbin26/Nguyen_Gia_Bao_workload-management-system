---
name: pulp-staff-assignment
description: >-
  Implements staff assignment for Workforce Management — greedy MVP first, PuLP ILP
  for batch/ai_suggestions. Use when working on assignment_service.py, ETC/PuLP
  algorithm, pick_best_staff, solve_batch_assignment, or ai_suggestions matching_score.
---

# Staff Assignment — Greedy MVP → PuLP ILP

Target: `services/assignment_service.py` (called by `POST /tasks`, `next-step`, `GET /analytics/overloads`).

Full ILP formulas: `.cursor/rules/04-thuat-toan-pulp-etc.mdc`.

## Step 1 — MVP: greedy (required for 6 APIs)

No PuLP needed for basic 1-to-1 assignment:

```python
def pick_best_staff(candidates: list[dict], duration_hours: float) -> dict | None:
    """candidates: staff docs in one department, status != 'Nghỉ phép'."""
    eligible = [
        s for s in candidates
        if s["workload_caps"]["current_daily_tasks"] + 1 <= s["workload_caps"]["max_daily_tasks"]
        and s["workload_caps"]["current_daily_hours"] + duration_hours <= s["workload_caps"]["max_daily_hours"]
    ]
    if not eligible:
        return None
    return min(eligible, key=lambda s: s["workload_caps"]["current_daily_hours"])
```

Write unit tests **before** wiring to router (`06-testing-checklist.mdc`).

## Step 2 — When PuLP (ILP) is actually needed

Only for **multi-task global optimization**, not sequential 1-to-1:

- Batch rebalance of many `"Chờ xử lý"` tasks
- Ranked `ai_suggestions` with `matching_score` for `GET /analytics/overloads`
- Phase 3 capability matrix assignment

## Step 3 — PuLP setup

```bash
pip install pulp
```

**Decision variables:** `x[i][j] ∈ {0,1}` — task `i` → staff `j`.

| Constraint | Rule |
|------------|------|
| 1 | Each task assigned exactly once: `Σ_j x[i][j] = 1` |
| 2 | Hours cap: `current_daily_hours[j] + Σ_i x[i][j]*duration[i] <= max_daily_hours[j]` |
| 3 | Task cap: `current_daily_tasks[j] + Σ_i x[i][j] <= max_daily_tasks[j]` |
| 4 | Department match: `x[i][j]=1` only if same department |
| Objective | Minimize `Σ x[i][j] * current_daily_hours[j]` (lowest ETC first) |

## Performance & fallback

- Scale ~15 staff / 3 depts → `PULP_CBC_CMD` solves in ms; always `msg=False`.
- If `prob.solve()` ≠ `Optimal` (e.g. `Infeasible`): return no assignment + create `overload_logs` — **never crash**.

## Done when

- [ ] Correctly chose greedy vs ILP for the use case
- [ ] PuLP constraints and objective defined if using ILP
- [ ] Infeasible/non-optimal fallback in place
