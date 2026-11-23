from asyncio import Semaphore, to_thread
from uuid import UUID

from src.repositories.knowledge import KnowledgeRepository
from src.schemas.knowledge import ContactOrigin, DocumentFormat, KnowledgeFile, KnowledgeInput, KnowledgeSource, WelcomeMessage
from src.services.knowledge_documents import DocumentImportError, MAX_DOCUMENT_TEXT, extract_document, extract_url
from src.services.integrations import IntegrationService


class KnowledgeUnavailable(Exception):
    pass


CHUNK_OVERLAP = 200
CHUNK_SIZE = 1800


class KnowledgeService:
    def __init__(self, repository: KnowledgeRepository, integrations: IntegrationService, url_origin: str | None = None) -> None:
        self._repository = repository
        self._integrations = integrations
        self._url_origin = url_origin
        self._imports = Semaphore(2)

    async def welcome(self, tenant_id: UUID, content: WelcomeMessage | None = None) -> WelcomeMessage:
        return await self._repository.welcome(tenant_id, content)

    async def origins(self, tenant_id: UUID) -> list[ContactOrigin]:
        return await self._repository.origins(tenant_id)

    async def save_origin(self, tenant_id: UUID, origin: ContactOrigin) -> ContactOrigin:
        await self._repository.save_origin(tenant_id, origin)
        return origin

    async def ingest_document(self, tenant_id: UUID, source: str, kind: DocumentFormat, raw: bytes) -> KnowledgeSource:
        async with self._imports:
            document = await to_thread(extract_document, kind, raw)
            document = document.strip()
            if not document:
                hint = " Aplique OCR se o PDF for escaneado." if kind == "pdf" else ""
                raise DocumentImportError(f"O arquivo não contém texto extraível.{hint}")
            if len(document) > MAX_DOCUMENT_TEXT:
                raise DocumentImportError("O arquivo tem mais de 40.000 caracteres de texto. Divida-o em partes menores.")
            return await self.ingest(tenant_id, KnowledgeInput(source=source, text=document),
                                     original=KnowledgeFile(kind=kind, content=raw))

    async def ingest_url(self, tenant_id: UUID, source: str, url: str) -> KnowledgeSource:
        async with self._imports:
            try:
                document = await to_thread(extract_url, url, self._url_origin)
            except (OSError, LookupError):
                raise KnowledgeUnavailable from None
            return await self.ingest(tenant_id, KnowledgeInput(source=source, text=document))

    async def ingest(self, tenant_id: UUID, content: KnowledgeInput, *, original: KnowledgeFile | None = None) -> KnowledgeSource:
        client = await self._integrations.ai(tenant_id)
        if client is None:
            raise KnowledgeUnavailable
        source, document = content.source.strip(), content.text.strip()
        if not source or not document:
            raise ValueError("Informe uma fonte e o conteúdo")
        # shortcut: split by characters for the pilot, use token-aware chunks for larger imports.
        chunks = [document[start:start + CHUNK_SIZE]
                  for start in range(0, max(1, len(document) - CHUNK_OVERLAP), CHUNK_SIZE - CHUNK_OVERLAP)]
        try:
            embeddings = await client.embed_batch(chunks)
        except (OSError, ValueError):
            raise KnowledgeUnavailable from None
        source = await self._repository.replace(tenant_id, source, list(zip(chunks, embeddings, strict=True)),
                                                client.embedding_space, original=original)
        return KnowledgeSource(source=source, chunks=len(chunks))

    async def download(self, tenant_id: UUID, source: str) -> KnowledgeFile | None:
        original, chunks = await self._repository.download(tenant_id, source)
        if original or not chunks:
            return original
        document = chunks[0] + "".join(chunk[CHUNK_OVERLAP:] for chunk in chunks[1:])
        return KnowledgeFile(kind="txt", content=document.encode("utf-8"))

    async def sources(self, tenant_id: UUID) -> list[KnowledgeSource]:
        return await self._repository.sources(tenant_id)

    async def delete(self, tenant_id: UUID, source: str) -> None:
        await self._repository.replace(tenant_id, source, [])
