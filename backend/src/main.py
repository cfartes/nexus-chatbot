from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import create_async_engine

from src.api.routes.auth import router as auth_router
from src.api.routes.clients import router as clients_router
from src.api.routes.conversations import router as conversations_router
from src.api.routes.health import router as health_router
from src.api.routes.integrations import router as integrations_router
from src.api.routes.knowledge import router as knowledge_router
from src.api.routes.openwa_webhook import router as openwa_webhook_router
from src.api.routes.operators import router as operators_router
from src.api.routes.whatsapp import router as whatsapp_router
from src.repositories.auth import AuthRepository
from src.repositories.bot import BotRepository
from src.repositories.conversations import ConversationRepository
from src.repositories.database import verify_runtime_access
from src.repositories.events import EventRepository
from src.repositories.incoming_messages import IncomingMessageRepository
from src.repositories.integrations import IntegrationRepository
from src.repositories.knowledge import KnowledgeRepository
from src.repositories.outgoing_messages import OutgoingMessageRepository
from src.repositories.operators import OperatorRepository
from src.repositories.tenants import TenantRepository
from src.services.auth import AuthService
from src.services.bot import BotService
from src.services.clients import ClientService
from src.services.conversations import ConversationService
from src.services.events import ConversationEvents
from src.services.knowledge import KnowledgeService
from src.services.integrations import IntegrationService
from src.services.openwa_webhook import OpenWAWebhook
from src.services.operators import OperatorService
from src.services.whatsapp import WhatsAppService
from src.settings import Settings


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncIterator[None]:
    settings = Settings()
    webhook_credentials = settings.webhook_credentials()
    engine = create_async_engine(settings.runtime_database_url(), pool_pre_ping=True, hide_parameters=True)
    try:
        await verify_runtime_access(engine)
        tenants = TenantRepository(engine)
        integrations = IntegrationService(IntegrationRepository(engine), settings)
        application.state.integrations = integrations
        application.state.tenant_repository = tenants
        application.state.whatsapp_service = WhatsAppService(tenants, integrations)
        application.state.auth_service = AuthService(AuthRepository(engine), settings.openwa_webhook_tenant_id)
        operators = OperatorService(OperatorRepository(engine), integrations, settings.public_origin)
        application.state.operator_service = operators
        application.state.client_service = ClientService(tenants, operators, settings.openwa_webhook_tenant_id)
        application.state.conversation_service = ConversationService(
            ConversationRepository(engine), OutgoingMessageRepository(engine), BotRepository(engine), integrations,
        )
        application.state.conversation_events = ConversationEvents(EventRepository(engine))
        knowledge = KnowledgeRepository(engine)
        application.state.knowledge_service = KnowledgeService(knowledge, integrations, settings.knowledge_url_origin)
        application.state.bot_service = BotService(BotRepository(engine), knowledge, integrations, settings.technical_web_sources)
        application.state.openwa_webhook = (
            OpenWAWebhook(IncomingMessageRepository(engine), *webhook_credentials, integrations)
            if webhook_credentials else None
        )
        application.state.public_origin = settings.public_origin
        yield
    finally:
        await engine.dispose()


app = FastAPI(title="Nexus Atende", lifespan=lifespan)
app.include_router(health_router, prefix="/api/v1")
app.include_router(auth_router, prefix="/api/v1")
app.include_router(clients_router, prefix="/api/v1")
app.include_router(conversations_router, prefix="/api/v1")
app.include_router(knowledge_router, prefix="/api/v1")
app.include_router(integrations_router, prefix="/api/v1")
app.include_router(operators_router, prefix="/api/v1")
app.include_router(whatsapp_router, prefix="/api/v1")
app.include_router(openwa_webhook_router, prefix="/api/v1")


@app.exception_handler(RequestValidationError)
async def request_validation_error(_request: Request, error: RequestValidationError) -> JSONResponse:
    return JSONResponse(status_code=422, content={"detail": [
        {"loc": issue["loc"], "type": issue["type"]} for issue in error.errors()
    ]})
