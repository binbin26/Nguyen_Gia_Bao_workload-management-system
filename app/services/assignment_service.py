"""
Staff assignment — greedy MVP (1 task → 1 staff).

Per 04-thuat-toan-pulp-etc.mdc: argmin(ETC) among eligible candidates.
No PuLP for single-task assignment.
"""

from typing import Any


def pick_best_staff(
    candidates: list[dict[str, Any]],
    duration_hours: float,
) -> dict[str, Any] | None:
    """
    Chọn cán bộ có ETC thấp nhất trong phòng ban sau khi lọc an toàn.

    Args:
        candidates: Danh sách staff document cùng phòng ban (dict từ MongoDB).
        duration_hours: Thời lượng chuẩn của công việc cần gán (giờ).

    Returns:
        Staff document được chọn, hoặc None nếu không còn ai đủ điều kiện
        (toàn bộ phòng ban đạt trần hoặc đang nghỉ phép).
    """
    eligible = [
        staff
        for staff in candidates
        if staff.get("status") != "Nghỉ phép"
        and _can_accept_projected_workload(staff, duration_hours)
    ]

    if not eligible:
        return None

    return min(
        eligible,
        key=lambda s: s["workload_caps"]["current_daily_hours"],
    )


def _can_accept_projected_workload(
    staff: dict[str, Any],
    duration_hours: float,
) -> bool:
    """Kiểm tra dự phóng tải lượng SAU khi cộng thêm việc mới (03-sau-api §1.5)."""
    caps = staff["workload_caps"]
    projected_tasks = caps["current_daily_tasks"] + 1
    projected_hours = caps["current_daily_hours"] + duration_hours

    return (
        projected_tasks <= caps["max_daily_tasks"]
        and projected_hours <= caps["max_daily_hours"]
    )
