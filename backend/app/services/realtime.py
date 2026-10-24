"""Websocket connection registry and the outbox pump.

Websockets are a latency optimisation, not the source of truth. Every message
means "go re-read your assignment". A player that never receives one still
converges through its polling fallback, and a reconnecting player always
re-reads from the database.

The pump tails the event_outbox table from this process's own cursor, so each
API process delivers to the sockets it holds. That keeps broadcast correct
when more than one process is running, without introducing Redis.
"""

import asyncio
import logging
from typing import Dict, Optional, Set

from fastapi import WebSocket

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.services import events

logger = logging.getLogger(__name__)


class ConnectionRegistry:
    def __init__(self) -> None:
        self._devices: Dict[int, Set[WebSocket]] = {}
        self._admins: Set[WebSocket] = set()
        self._lock = asyncio.Lock()
        self._subscribed = asyncio.Event()

    async def add_device(self, display_id: int, socket: WebSocket) -> None:
        async with self._lock:
            self._devices.setdefault(display_id, set()).add(socket)
            self._subscribed.set()

    async def remove_device(self, display_id: int, socket: WebSocket) -> None:
        async with self._lock:
            sockets = self._devices.get(display_id)
            if not sockets:
                return
            sockets.discard(socket)
            if not sockets:
                self._devices.pop(display_id, None)
            if not self._devices and not self._admins:
                self._subscribed.clear()

    async def add_admin(self, socket: WebSocket) -> None:
        async with self._lock:
            self._admins.add(socket)
            self._subscribed.set()

    async def remove_admin(self, socket: WebSocket) -> None:
        async with self._lock:
            self._admins.discard(socket)
            if not self._devices and not self._admins:
                self._subscribed.clear()

    async def wait_for_subscribers(self) -> None:
        await self._subscribed.wait()

    def reset_waiter(self) -> None:
        # Application lifespans can restart on a different event loop.
        self._subscribed = asyncio.Event()
        if self._devices or self._admins:
            self._subscribed.set()

    async def send_to_device(self, display_id: int, message: dict) -> None:
        async with self._lock:
            sockets = list(self._devices.get(display_id, ()))
        await self._fan_out(sockets, message)

    async def send_to_admins(self, message: dict) -> None:
        async with self._lock:
            sockets = list(self._admins)
        await self._fan_out(sockets, message)

    async def _fan_out(self, sockets, message: dict) -> None:
        for socket in sockets:
            try:
                await socket.send_json(message)
            except Exception:
                # A dead socket is normal; the disconnect handler cleans up.
                logger.debug("Dropping websocket send", exc_info=True)

    def device_count(self) -> int:
        return sum(len(s) for s in self._devices.values())

    def admin_count(self) -> int:
        return len(self._admins)


registry = ConnectionRegistry()


class EventPump:
    """Polls the outbox and pushes events onto local sockets."""

    def __init__(self) -> None:
        self._task: Optional[asyncio.Task] = None
        self._stop = asyncio.Event()
        self._cursor = 0

    async def start(self) -> None:
        if self._task is not None:
            return
        self._cursor = await asyncio.to_thread(self._initial_cursor)
        self._stop = asyncio.Event()
        registry.reset_waiter()
        self._task = asyncio.create_task(self._run(), name="event-pump")

    async def stop(self) -> None:
        self._stop.set()
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):
                pass
            self._task = None

    def _initial_cursor(self) -> int:
        """Start from now: a restart must not replay yesterday's events."""
        db = SessionLocal()
        try:
            return events.latest_event_id(db)
        finally:
            db.close()

    def _drain(self):
        db = SessionLocal()
        try:
            rows = events.events_after(db, self._cursor, limit=200)
            return [
                {
                    "id": row.id,
                    "topic": row.topic,
                    "display_id": row.display_id,
                    "payload": row.payload or {},
                }
                for row in rows
            ]
        finally:
            db.close()

    async def _run(self) -> None:
        settings = get_settings()
        while not self._stop.is_set():
            try:
                # No websocket clients means there is nobody to notify. Sleep
                # until a connection arrives instead of querying SQL all day.
                await registry.wait_for_subscribers()
                batch = await asyncio.to_thread(self._drain)
                for item in batch:
                    self._cursor = max(self._cursor, item["id"])
                    message = {"type": item["topic"], **item["payload"]}

                    if item["display_id"] is not None and item["topic"] in (
                        events.TOPIC_ASSIGNMENT, events.TOPIC_COMMAND, events.TOPIC_REVOKED,
                    ):
                        await registry.send_to_device(item["display_id"], message)

                    await registry.send_to_admins(
                        {**message, "display_id": item["display_id"]}
                    )
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Event pump iteration failed")

            try:
                await asyncio.wait_for(
                    self._stop.wait(), timeout=settings.event_poll_interval_seconds
                )
            except asyncio.TimeoutError:
                continue


pump = EventPump()
