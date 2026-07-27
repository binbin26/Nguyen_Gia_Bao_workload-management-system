from __future__ import annotations

import jwt
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.core.config import settings
from app.core.roles import RoleEnum
from app.core.security import ACCESS_COOKIE_NAME, decode_token
from app.services.websocket_manager import websocket_manager

router = APIRouter(tags=["realtime"])


@router.websocket("/api/v1/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    origin = websocket.headers.get("origin")
    if origin not in settings.CORS_ALLOWED_ORIGINS:
        await websocket.close(code=1008)
        return

    access_token = websocket.cookies.get(ACCESS_COOKIE_NAME)
    if not access_token:
        await websocket.close(code=1008)
        return

    try:
        user = decode_token(access_token, expected_type="access")
    except jwt.InvalidTokenError:
        await websocket.close(code=1008)
        return

    if user.get("role") != RoleEnum.MANAGER:
        await websocket.close(code=1008)
        return

    await websocket_manager.connect(websocket)

    try:
        while True:
            # Client heartbeat frames keep the connection alive through proxies.
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        websocket_manager.disconnect(websocket)
