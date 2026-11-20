from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response

from src.api.routes.auth import administrator, administrator_mutation
from src.schemas.auth import Operator
from src.schemas.knowledge import KnowledgeInput, KnowledgeSource, KnowledgeURL
from src.services.knowledge import KnowledgeService, KnowledgeUnavailable
from src.services.knowledge_documents import MAX_UPLOAD, DocumentFormat

router = APIRouter(prefix="/knowledge")


def knowledge_service(request: Request) -> KnowledgeService:
    service: KnowledgeService = request.app.state.knowledge_service
    return service


Service = Annotated[KnowledgeService, Depends(knowledge_service)]
Reader = Annotated[Operator, Depends(administrator)]
Writer = Annotated[Operator, Depends(administrator_mutation)]


@router.get("")
async def sources(actor: Reader, service: Service, response: Response) -> list[KnowledgeSource]:
    response.headers["Cache-Control"] = "no-store"
    return await service.sources(actor.tenant_id)


@router.put("")
async def ingest(content: KnowledgeInput, actor: Writer, service: Service) -> KnowledgeSource:
    try:
        return await service.ingest(actor.tenant_id, content)
    except KnowledgeUnavailable:
        raise HTTPException(503, "Serviço de vetorização indisponível") from None
    except ValueError:
        raise HTTPException(422, "Informe uma fonte e o conteúdo") from None


@router.put("/file")
async def ingest_file(
    request: Request, actor: Writer, service: Service, kind: DocumentFormat,
    source: Annotated[str, Query(min_length=1, max_length=200)],
) -> KnowledgeSource:
    raw = bytearray()
    async for chunk in request.stream():
        if len(raw) + len(chunk) > MAX_UPLOAD:
            raise HTTPException(413, "Arquivo maior que 4 MiB")
        raw.extend(chunk)
    try:
        return await service.ingest_document(actor.tenant_id, source, kind, bytes(raw))
    except KnowledgeUnavailable:
        raise HTTPException(503, "Serviço de vetorização indisponível") from None
    except ValueError:
        raise HTTPException(422, "Arquivo inválido, sem texto ou com mais de 40.000 caracteres") from None


@router.put("/url")
async def ingest_url(content: KnowledgeURL, actor: Writer, service: Service) -> KnowledgeSource:
    try:
        return await service.ingest_url(actor.tenant_id, content.source, content.url)
    except KnowledgeUnavailable:
        raise HTTPException(503, "Página ou serviço de vetorização indisponível") from None
    except ValueError:
        raise HTTPException(422, "URL ou conteúdo fora dos limites de importação") from None


@router.delete("", status_code=204)
async def delete(source: Annotated[str, Query(min_length=1, max_length=200)], actor: Writer, service: Service) -> Response:
    if "\x00" in source:
        raise HTTPException(422, "Fonte inválida")
    await service.delete(actor.tenant_id, source.strip())
    return Response(status_code=204)
