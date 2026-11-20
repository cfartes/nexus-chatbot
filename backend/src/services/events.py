from asyncio import Semaphore, wait_for
from collections.abc import AsyncIterator
from uuid import UUID

from src.repositories.events import EventRepository


class ConversationEvents:
    def __init__(self, repository: EventRepository) -> None:
        self._repository = repository
        self._streams = Semaphore(5)

    async def stream(self, tenant_id: UUID) -> AsyncIterator[str]:
        if self._streams.locked():
            yield "retry: 10000\n\n"
            return
        async with self._streams, self._repository.listen(tenant_id) as changed:
            yield "event: change\ndata: {}\n\n"
            # Reconnect periodically so session rights are revalidated.
            for _ in range(12):
                try:
                    await wait_for(changed.wait(), timeout=5)
                except TimeoutError:
                    yield ": heartbeat\n\n"
                else:
                    changed.clear()
                    yield "event: change\ndata: {}\n\n"
