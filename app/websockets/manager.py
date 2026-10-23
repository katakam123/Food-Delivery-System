
import asyncio
from collections import defaultdict

from fastapi import WebSocket


class ConnectionManager:
    def __init__(self):
        self.order_connections = defaultdict(dict)
        self.restaurant_connections = defaultdict(dict)
        self.partner_connections = defaultdict(dict)

        # Protect shared connection dictionaries when connections are
        # added or removed concurrently.
        self.lock = asyncio.Lock()

    async def connect_order(self, order_id: int, user_id: int, ws: WebSocket):
        await ws.accept()
        async with self.lock:
            self.order_connections[order_id][user_id] = ws

    async def connect_restaurant(
        self, owner_id: int, ws: WebSocket
    ):
        await ws.accept()
        async with self.lock:
            self.restaurant_connections[owner_id][id(ws)] = ws

    async def connect_partner(self, partner_user_id: int, ws: WebSocket):
        await ws.accept()
        async with self.lock:
            self.partner_connections[partner_user_id][id(ws)] = ws

    async def disconnect_order(
        self, order_id: int, user_id: int, ws: WebSocket
    ):
        async with self.lock:
            connections = self.order_connections.get(order_id, {})
            if connections.get(user_id) is ws:
                connections.pop(user_id, None)
            if not connections:
                self.order_connections.pop(order_id, None)

    async def disconnect_restaurant(self, owner_id: int, ws: WebSocket):
        async with self.lock:
            connections = self.restaurant_connections.get(owner_id, {})
            connections.pop(id(ws), None)
            if not connections:
                self.restaurant_connections.pop(owner_id, None)

    async def disconnect_partner(self, partner_user_id: int, ws: WebSocket):
        async with self.lock:
            connections = self.partner_connections.get(
                partner_user_id, {}
            )
            connections.pop(id(ws), None)
            if not connections:
                self.partner_connections.pop(partner_user_id, None)

    async def send_order(self, order_id: int, message: dict):
        async with self.lock:
            connections = list(
                self.order_connections.get(order_id, {}).items()
            )

        disconnected = []
        for user_id, ws in connections:
            try:
                await ws.send_json(message)
            except Exception:
                disconnected.append((user_id, ws))

        for user_id, ws in disconnected:
            await self.disconnect_order(order_id, user_id, ws)

    async def send_restaurant(self, owner_id: int, message: dict):
        async with self.lock:
            connections = list(
                self.restaurant_connections.get(owner_id, {}).items()
            )

        disconnected = []
        for connection_id, ws in connections:
            try:
                await ws.send_json(message)
            except Exception:
                disconnected.append((connection_id, ws))

        for connection_id, ws in disconnected:
            async with self.lock:
                current = self.restaurant_connections.get(owner_id, {})
                if current.get(connection_id) is ws:
                    current.pop(connection_id, None)

    async def send_partner(self, partner_user_id: int, message: dict):
        async with self.lock:
            connections = list(
                self.partner_connections.get(partner_user_id, {}).items()
            )

        disconnected = []
        for connection_id, ws in connections:
            try:
                await ws.send_json(message)
            except Exception:
                disconnected.append((connection_id, ws))

        for connection_id, ws in disconnected:
            async with self.lock:
                current = self.partner_connections.get(
                    partner_user_id, {}
                )
                if current.get(connection_id) is ws:
                    current.pop(connection_id, None)


manager = ConnectionManager()
