from asyncio import Semaphore, to_thread
from uuid import UUID

from src.repositories.knowledge import KnowledgeRepository
from src.schemas.knowledge import KnowledgeInput, KnowledgeSource
from src.services.knowledge_documents import DocumentFormat, extract_document, extract_url
from src.services.openai import OpenAIClient


class KnowledgeUnavailable(Exception):
    pass


class KnowledgeService:
    def __init__(self, repository: KnowledgeRepository, client: OpenAIClient | None, url_origin: str | None = None) -> None:
        self._repository = repository
        self._client = client
        self._url_origin = url_origin
        self._imports = Semaphore(2)

    async def ingest_document(self, tenant_id: UUID, source: str, kind: DocumentFormat, raw: bytes) -> KnowledgeSource:
        async with self._imports:
            document = await to_thread(extract_document, kind, raw)
            return await self.ingest(tenant_id, KnowledgeInput(source=source, text=document))

    async def ingest_url(self, tenant_id: UUID, source: str, url: str) -> KnowledgeSource:
        async with self._imports:
            try:
                document = await to_thread(extract_url, url, self._url_origin)
            except (OSError, LookupError):
                raise KnowledgeUnavailable from None
            return await self.ingest(tenant_id, KnowledgeInput(source=source, text=document))

    async def ingest(self, tenant_id: UUID, content: KnowledgeInput) -> KnowledgeSource:
        if self._client is None:
            raise KnowledgeUnavailable
        source, document = content.source.strip(), content.text.strip()
        if not source or not document:
            raise ValueError("Informe uma fonte e o conteúdo")
        # shortcut: split by characters for the pilot, use token-aware chunks for larger imports.
        chunks = [document[start:start + 1800] for start in range(0, max(1, len(document) - 200), 1600)]
        try:
            embeddings = await self._client.embed_batch(chunks)
        except (OSError, ValueError):
            raise KnowledgeUnavailable from None
        await self._repository.replace(tenant_id, source, list(zip(chunks, embeddings, strict=True)))
        return KnowledgeSource(source=source, chunks=len(chunks))

    async def sources(self, tenant_id: UUID) -> list[KnowledgeSource]:
        return await self._repository.sources(tenant_id)

    async def delete(self, tenant_id: UUID, source: str) -> None:
        await self._repository.replace(tenant_id, source, [])
