"""WebSocket connection manager with broadcast and throttling."""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any

from fastapi import WebSocket


class ConnectionManager:
    """Manages WebSocket connections for admin and driver dashboards."""

    def __init__(self, max_updates_per_sec: int = 10):
        self._admin_connections: dict[str, list[WebSocket]] = {}   # sim_id -> [ws]
        self._driver_connections: dict[str, dict[str, WebSocket]] = {}  # sim_id -> {ev_id: ws}
        self._min_interval = 1.0 / max(1, max_updates_per_sec)
        self._last_broadcast: dict[str, float] = {}

    async def connect_admin(self, websocket: WebSocket, sim_id: str) -> None:
        await websocket.accept()
        if sim_id not in self._admin_connections:
            self._admin_connections[sim_id] = []
        self._admin_connections[sim_id].append(websocket)

    async def connect_driver(self, websocket: WebSocket, sim_id: str,
                             ev_id: str) -> None:
        await websocket.accept()
        if sim_id not in self._driver_connections:
            self._driver_connections[sim_id] = {}
        self._driver_connections[sim_id][ev_id] = websocket

    def disconnect_admin(self, websocket: WebSocket, sim_id: str) -> None:
        if sim_id in self._admin_connections:
            self._admin_connections[sim_id] = [
                ws for ws in self._admin_connections[sim_id] if ws != websocket
            ]

    def disconnect_driver(self, sim_id: str, ev_id: str) -> None:
        if sim_id in self._driver_connections:
            self._driver_connections[sim_id].pop(ev_id, None)

    async def broadcast_admin(self, sim_id: str, message: dict) -> None:
        """Broadcast to all admin connections for a simulation, with throttling."""
        key = f"admin:{sim_id}"
        now = time.monotonic()
        last = self._last_broadcast.get(key, 0)
        if now - last < self._min_interval:
            return
        self._last_broadcast[key] = now

        if sim_id not in self._admin_connections:
            return

        data = json.dumps(message)
        dead: list[WebSocket] = []
        for ws in self._admin_connections[sim_id]:
            try:
                await ws.send_text(data)
            except Exception:
                dead.append(ws)

        for ws in dead:
            self._admin_connections[sim_id].remove(ws)

    async def send_driver(self, sim_id: str, ev_id: str, message: dict) -> None:
        """Send message to a specific driver connection."""
        ws = self._driver_connections.get(sim_id, {}).get(ev_id)
        if ws is None:
            return
        try:
            await ws.send_text(json.dumps(message))
        except Exception:
            self.disconnect_driver(sim_id, ev_id)

    async def broadcast_all_drivers(self, sim_id: str, message: dict) -> None:
        """Broadcast to all driver connections for a simulation."""
        if sim_id not in self._driver_connections:
            return
        data = json.dumps(message)
        dead: list[str] = []
        for ev_id, ws in self._driver_connections[sim_id].items():
            try:
                await ws.send_text(data)
            except Exception:
                dead.append(ev_id)
        for ev_id in dead:
            self._driver_connections[sim_id].pop(ev_id, None)

    def admin_count(self, sim_id: str) -> int:
        return len(self._admin_connections.get(sim_id, []))

    def driver_count(self, sim_id: str) -> int:
        return len(self._driver_connections.get(sim_id, {}))


# Global instance
ws_manager = ConnectionManager()
