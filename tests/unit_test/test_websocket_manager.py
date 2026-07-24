import unittest
from typing import Any

from app.services.websocket_manager import WebSocketManager


class FakeWebSocket:
    def __init__(self) -> None:
        self.accepted = False
        self.messages: list[dict[str, Any]] = []

    async def accept(self) -> None:
        self.accepted = True

    async def send_json(self, message: dict[str, Any]) -> None:
        self.messages.append(message)


class WebSocketManagerTests(unittest.IsolatedAsyncioTestCase):
    async def test_broadcast_sends_the_event_to_every_connected_client(self) -> None:
        manager = WebSocketManager()
        first_client = FakeWebSocket()
        second_client = FakeWebSocket()
        event = {"type": "overload.resolved", "payload": {"log_id": "log-1"}}

        await manager.connect(first_client)  # type: ignore[arg-type]
        await manager.connect(second_client)  # type: ignore[arg-type]

        delivered = await manager.broadcast_json(event)

        self.assertEqual(delivered, 2)
        self.assertEqual(first_client.messages, [event])
        self.assertEqual(second_client.messages, [event])


if __name__ == "__main__":
    unittest.main()
