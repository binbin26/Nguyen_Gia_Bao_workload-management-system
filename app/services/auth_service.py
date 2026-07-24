from datetime import datetime, timezone
from typing import Any

import bcrypt
import jwt
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.security import (
    TokenPair,
    create_token_pair,
    decode_token,
    hash_refresh_jti,
)

INVALID_CREDENTIALS = "INVALID_CREDENTIALS"
INVALID_REFRESH_SESSION = "INVALID_REFRESH_SESSION"

# Perform the same expensive bcrypt operation even when the username does not
# exist, reducing the timing difference attackers can use for enumeration.
DUMMY_PASSWORD_HASH = bcrypt.hashpw(
    b"constant-time-dummy-password",
    bcrypt.gensalt(),
).decode("utf-8")


def verify_password(plain_password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(
            plain_password.encode("utf-8"),
            password_hash.encode("utf-8"),
        )
    except ValueError:
        return False


def create_access_token(user: dict[str, Any]) -> str:
    """Backward-compatible helper for scripts; browsers receive cookies instead."""
    return create_token_pair(user).access_token


def public_user(user: dict[str, Any]) -> dict[str, Any]:
    return {
        "username": str(user["_id"]),
        "role": user["role"],
        "staff_id": user.get("staff_id"),
    }


async def store_refresh_session(
    db: AsyncIOMotorDatabase,
    *,
    user_id: str,
    tokens: TokenPair,
) -> None:
    await db.refresh_sessions.insert_one(
        {
            "_id": hash_refresh_jti(tokens.refresh_jti),
            "user_id": user_id,
            "session_id": tokens.session_id,
            "expires_at": tokens.refresh_expires_at,
            "created_at": datetime.now(timezone.utc),
        }
    )


async def login_user(
    db: AsyncIOMotorDatabase,
    *,
    username: str,
    password: str,
) -> tuple[dict[str, Any], TokenPair]:
    user = await db.users.find_one({"_id": username})
    password_hash = user.get("password_hash", "") if user else DUMMY_PASSWORD_HASH
    password_is_valid = verify_password(password, password_hash)
    if user is None or not password_is_valid:
        raise ValueError(INVALID_CREDENTIALS)

    tokens = create_token_pair(user)
    await store_refresh_session(db, user_id=str(user["_id"]), tokens=tokens)
    return public_user(user), tokens


async def rotate_refresh_session(
    db: AsyncIOMotorDatabase,
    refresh_token: str,
) -> tuple[dict[str, Any], TokenPair]:
    """Atomically consume a refresh token and replace it to prevent replay."""
    try:
        payload = decode_token(refresh_token, expected_type="refresh")
    except jwt.InvalidTokenError as exc:
        raise ValueError(INVALID_REFRESH_SESSION) from exc

    session = await db.refresh_sessions.find_one_and_delete(
        {
            "_id": hash_refresh_jti(payload["jti"]),
            "user_id": payload["sub"],
            "session_id": payload["sid"],
            "expires_at": {"$gt": datetime.now(timezone.utc)},
        }
    )
    if session is None:
        raise ValueError(INVALID_REFRESH_SESSION)

    user = await db.users.find_one({"_id": payload["sub"]})
    if user is None:
        raise ValueError(INVALID_REFRESH_SESSION)

    tokens = create_token_pair(user, session_id=payload["sid"])
    await store_refresh_session(db, user_id=str(user["_id"]), tokens=tokens)
    return public_user(user), tokens


async def revoke_refresh_session(
    db: AsyncIOMotorDatabase,
    refresh_token: str | None,
) -> None:
    if not refresh_token:
        return
    try:
        payload = decode_token(
            refresh_token,
            expected_type="refresh",
            verify_expiration=False,
        )
    except jwt.InvalidTokenError:
        return
    await db.refresh_sessions.delete_one(
        {
            "_id": hash_refresh_jti(payload["jti"]),
            "user_id": payload["sub"],
        }
    )
