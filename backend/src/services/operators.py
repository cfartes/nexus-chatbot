from asyncio import Semaphore, to_thread
from uuid import UUID

from src.repositories.operators import OperatorRepository
from src.schemas.operators import OperatorCreate, OperatorRecord, OperatorUpdate
from src.services.passwords import hash_password


class OperatorService:
    def __init__(self, repository: OperatorRepository) -> None:
        self._repository = repository
        self._slots = Semaphore(2)

    async def list(self, tenant_id: UUID) -> list[OperatorRecord]:
        return await self._repository.list(tenant_id)

    async def create(self, tenant_id: UUID, operator: OperatorCreate) -> OperatorRecord | None:
        name = operator.name.strip()
        if not name:
            raise ValueError("Informe o nome")
        async with self._slots:
            password_hash = await to_thread(hash_password, operator.password.get_secret_value())
        return await self._repository.create(tenant_id, name, operator.email.lower(), password_hash)

    async def update(self, tenant_id: UUID, user_id: UUID, operator: OperatorUpdate) -> OperatorRecord | None:
        name = operator.name.strip()
        if not name:
            raise ValueError("Informe o nome")
        password_hash = None
        if operator.password:
            async with self._slots:
                password_hash = await to_thread(hash_password, operator.password.get_secret_value())
        return await self._repository.update(tenant_id, user_id, name, operator.is_active, password_hash)
