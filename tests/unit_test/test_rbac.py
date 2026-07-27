from typing import Annotated

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app.api.dependencies import (
    get_current_manager,
    get_current_user,
    require_role,
    verify_user_ownership,
)
from app.core.exceptions import AppHTTPException
from app.core.roles import AuthenticatedUser, RoleEnum


def _user(
    role: RoleEnum,
    *,
    staff_id: str | None = None,
    compatibility_id: str | int | None = None,
) -> AuthenticatedUser:
    user: AuthenticatedUser = {"sub": "test-user", "role": role}
    if staff_id is not None:
        user["staff_id"] = staff_id
    if compatibility_id is not None:
        user["id"] = compatibility_id
    return user


def _example_api(user: AuthenticatedUser) -> TestClient:
    """Build the two example endpoints from the RBAC contract."""
    app = FastAPI()
    app.dependency_overrides[get_current_user] = lambda: user

    @app.get(
        "/ai-suggestions",
        dependencies=[Depends(get_current_manager)],
    )
    def ai_suggestions() -> dict[str, list[str]]:
        return {"suggestions": []}

    @app.put("/tasks/{staff_id}")
    def update_staff_task(
        staff_id: str,
        _: Annotated[AuthenticatedUser, Depends(verify_user_ownership)],
    ) -> dict[str, str]:
        return {"staff_id": staff_id}

    return TestClient(app)


def test_require_role_accepts_enum_and_rejects_disallowed_role() -> None:
    manager_only = require_role(RoleEnum.MANAGER)
    manager = _user(RoleEnum.MANAGER)

    assert manager_only(manager) is manager

    with pytest.raises(AppHTTPException) as exc_info:
        manager_only(_user(RoleEnum.STAFF))

    assert exc_info.value.status_code == 403
    assert exc_info.value.error_code == "FORBIDDEN_ACCESS"


def test_require_role_rejects_an_empty_allow_list() -> None:
    with pytest.raises(ValueError):
        require_role()


@pytest.mark.parametrize(
    "user",
    [
        _user(RoleEnum.STAFF, staff_id="staff-01"),
        _user(RoleEnum.STAFF, compatibility_id=1),
        _user(RoleEnum.MANAGER),
    ],
)
def test_verify_user_ownership_allows_owner_and_manager(
    user: AuthenticatedUser,
) -> None:
    requested_staff_id = (
        str(user.get("staff_id") or user.get("id"))
        if user["role"] == RoleEnum.STAFF
        else "any-staff"
    )

    assert verify_user_ownership(requested_staff_id, user) is user


def test_verify_user_ownership_rejects_another_staff_member() -> None:
    with pytest.raises(AppHTTPException) as exc_info:
        verify_user_ownership(
            "staff-02",
            _user(RoleEnum.STAFF, staff_id="staff-01"),
        )

    assert exc_info.value.status_code == 403
    assert exc_info.value.error_code == "FORBIDDEN_RESOURCE_OWNERSHIP"


def test_example_ai_suggestions_endpoint_is_manager_only() -> None:
    manager_response = _example_api(_user(RoleEnum.MANAGER)).get(
        "/ai-suggestions"
    )
    staff_response = _example_api(_user(RoleEnum.STAFF)).get(
        "/ai-suggestions"
    )

    assert manager_response.status_code == 200
    assert staff_response.status_code == 403


def test_example_task_endpoint_enforces_data_ownership() -> None:
    staff_client = _example_api(_user(RoleEnum.STAFF, staff_id="staff-01"))

    assert staff_client.put("/tasks/staff-01").status_code == 200
    assert staff_client.put("/tasks/staff-02").status_code == 403
    assert (
        _example_api(_user(RoleEnum.MANAGER)).put("/tasks/staff-02").status_code
        == 200
    )
