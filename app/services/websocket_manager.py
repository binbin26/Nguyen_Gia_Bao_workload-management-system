from __future__ import annotations

import asyncio
from collections.abc import Mapping
from typing import Any

from fastapi import WebSocket


class WebSocketManager:
    """Keep and broadcast to every WebSocket connected to this process."""

    def __init__(self) -> None:
        self._connections: dict[WebSocket, asyncio.Lock] = {}

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self._connections[websocket] = asyncio.Lock()

    def disconnect(self, websocket: WebSocket) -> None:
        self._connections.pop(websocket, None)

    async def _send_json(
        self,
        websocket: WebSocket,
        lock: asyncio.Lock,
        message: Mapping[str, Any],
    ) -> bool:
        try:
            async with lock:
                await websocket.send_json(dict(message))
        except Exception:
            return False
        return True

    async def broadcast_json(self, message: Mapping[str, Any]) -> int:
        """Send to a stable snapshot of all clients and remove dead sockets."""
        connections = tuple(self._connections.items())
        if not connections:
            return 0

        results = await asyncio.gather(
            *(
                self._send_json(websocket, lock, message)
                for websocket, lock in connections
            )
        )

        delivered = 0
        for (websocket, _), succeeded in zip(connections, results, strict=True):
            if succeeded:
                delivered += 1
            else:
                self.disconnect(websocket)

        return delivered


websocket_manager = WebSocketManager()
