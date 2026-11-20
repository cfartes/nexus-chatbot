from asyncio import Event
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from typing import Protocol, cast
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncEngine


type Listener = Callable[[object, int, str, str], None]


class _NotificationConnection(Protocol):
    async def add_listener(self, channel: str, callback: Listener) -> None: ...
    async def remove_listener(self, channel: str, callback: Listener) -> None: ...


class EventRepository:
    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    @asynccontextmanager
    async def listen(self, tenant_id: UUID) -> AsyncIterator[Event]:
        event = Event()
        channel = f"nexus_atende_{tenant_id.hex}"

        def changed(_connection: object, _pid: int, _channel: str, _payload: str) -> None:
            event.set()

        async with self._engine.connect() as connection:
            raw = await connection.get_raw_connection()
            driver = cast(_NotificationConnection, raw.driver_connection)
            await driver.add_listener(channel, changed)
            try:
                yield event
            finally:
                await driver.remove_listener(channel, changed)
