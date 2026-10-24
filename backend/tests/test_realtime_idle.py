import asyncio

import pytest

from app.core.config import get_settings
from app.services import events, realtime


@pytest.mark.asyncio
async def test_event_pump_sleeps_without_subscribers_and_filters_device_events(monkeypatch):
    registry = realtime.ConnectionRegistry()
    monkeypatch.setattr(realtime, "registry", registry)
    monkeypatch.setattr(get_settings(), "event_poll_interval_seconds", 0.01)
    pump = realtime.EventPump()
    monkeypatch.setattr(pump, "_initial_cursor", lambda: 0)
    reads = []
    messages = []

    def drain():
        reads.append(True)
        if len(reads) > 1:
            return []
        return [
            {"id": 1, "topic": events.TOPIC_DISPLAY_STATE, "display_id": 1, "payload": {}},
            {"id": 2, "topic": events.TOPIC_ASSIGNMENT, "display_id": 1, "payload": {}},
        ]

    class Socket:
        async def send_json(self, message):
            messages.append(message)

    monkeypatch.setattr(pump, "_drain", drain)
    await pump.start()
    try:
        await asyncio.sleep(0.03)
        assert reads == []
        socket = Socket()
        await registry.add_device(1, socket)
        for _ in range(50):
            if messages:
                break
            await asyncio.sleep(0.01)
        assert [message["type"] for message in messages] == [events.TOPIC_ASSIGNMENT]
        await registry.remove_device(1, socket)
        await asyncio.sleep(0.03)
        previous_reads = len(reads)
        await asyncio.sleep(0.03)
        assert len(reads) == previous_reads
    finally:
        await pump.stop()
