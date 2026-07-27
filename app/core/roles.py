"""Shared role and authenticated-user types for RBAC checks."""

from enum import Enum
from typing import NotRequired, TypedDict


class RoleEnum(str, Enum):
    """Roles supported by the workforce-management application."""

    MANAGER = "manager"
    STAFF = "staff"


class AuthenticatedUser(TypedDict):
    """JWT claims consumed by authentication and authorization dependencies."""

    sub: str
    role: RoleEnum
    staff_id: NotRequired[str | None]
    # ``id`` is retained as a compatibility claim for external token issuers.
    id: NotRequired[str | int | None]
