from datetime import datetime, timedelta, timezone
from typing import Any

import bcrypt
import jwt
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.config import settings

INVALID_CREDENTIALS = "INVALID_CREDENTIALS"


def verify_password(plain_password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(
            plain_password.encode("utf-8"),
            password_hash.encode("utf-8"),
        )
    except ValueError:
        return False


def create_access_token(user: dict[str, Any]) -> str:
    expire_at = datetime.now(timezone.utc) + timedelta(
        minutes=settings.JWT_EXPIRE_MINUTES
    )
    payload: dict[str, Any] = {
        "sub": user["_id"],
        "role": user["role"],
        "exp": expire_at,
    }
    if user.get("staff_id") is not None:
        payload["staff_id"] = user["staff_id"]

    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


async def login_user(
    db: AsyncIOMotorDatabase,
    *,
    username: str,
    password: str,
) -> dict[str, Any]:
    user = await db.users.find_one({"_id": username})
    if user is None or not verify_password(password, user.get("password_hash", "")):
        raise ValueError(INVALID_CREDENTIALS)

    token = create_access_token(user)
    return {
        "access_token": token,
        "token_type": "bearer",
        "user": {
            "username": user["_id"],
            "role": user["role"],
            "staff_id": user.get("staff_id"),
        },
    }
