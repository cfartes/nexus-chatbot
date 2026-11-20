import asyncio
from email.message import Message
import json
import os
from http.cookies import SimpleCookie
from hmac import digest
from io import BytesIO
from urllib.error import HTTPError
from unittest.mock import patch
from uuid import UUID, uuid4
from zipfile import ZipFile

from cryptography.fernet import Fernet
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject
from pydantic import SecretStr
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from src.main import app
from src.repositories.database import tenant_transaction
from src.repositories.events import EventRepository
from src.repositories.integrations import IntegrationRepository
from src.repositories.work import enqueue
from src.schemas.integrations import OpenWASettings
from src.services.integrations import IntegrationService, tenant_webhook_secret
from src.settings import Settings
from src.worker import Worker
from tests.check_auth import request
from tests.check_conversations import login
from tests.check_webhook import OTHER, SECRET, SESSION, TENANT


def sample_pdf(content: bytes = b"Nexus em horario comercial") -> bytes:
    writer = PdfWriter()
    page = writer.add_blank_page(100, 100)
    page[NameObject("/Resources")] = DictionaryObject({NameObject("/Font"): DictionaryObject({
        NameObject("/F1"): DictionaryObject({NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"), NameObject("/BaseFont"): NameObject("/Helvetica")}),
    })})
    stream = DecodedStreamObject()
    stream.set_data(b"BT /F1 12 Tf 10 20 Td (" + content + b") Tj ET")
    page[NameObject("/Contents")] = stream
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


def sample_docx() -> bytes:
    output = BytesIO()
    with ZipFile(output, "w") as archive:
        archive.writestr("word/document.xml", '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
                         '<w:body><w:p><w:r><w:t>Nexus atende pelo WhatsApp</w:t></w:r></w:p></w:body></w:document>')
    return output.getvalue()


async def check() -> None:
    os.environ.update({
        "NEXUS_ATENDE_CONFIG_KEY": Fernet.generate_key().decode(),
        "NEXUS_ATENDE_OPENWA_ALLOWED_URLS": "https://secondary-openwa.example.test/api",
        "NEXUS_ATENDE_OLLAMA_URL": "http://127.0.0.1:11434",
        "NEXUS_ATENDE_OPENWA_WEBHOOK_TENANT_ID": str(TENANT), "NEXUS_ATENDE_OPENWA_WEBHOOK_SECRET": SECRET,
        "NEXUS_ATENDE_OPENAI_API_KEY": "test-only", "NEXUS_ATENDE_RESEND_API_KEY": "test-only",
        "NEXUS_ATENDE_RESEND_FROM": "from@example.test", "NEXUS_ATENDE_RESEND_TO": "to@example.test",
    })
    engine = create_async_engine(Settings().runtime_database_url())
    vector = {"data": [{"index": 0, "embedding": [1.0] + [0.0] * 767}]}
    completion = {"choices": [{"message": {"content": '{"needs_human": false, "answer": "Atendemos em horário comercial."}'}}]}
    try:
        worker = Worker(engine, Settings(), TENANT)
        async with (app.router.lifespan_context(app)):
            _, operator = await login(b"FIRST@EXAMPLE.TEST")
            _, admin = await login(b"ADMIN@EXAMPLE.TEST")

            async def call(prefix: str, method: str, path: str, body: object = None, *, admin_only: bool = True) -> tuple[int, bytes]:
                status, _, response = await request(method, path, json.dumps(body).encode() if body is not None else b"",
                                                    admin if admin_only else operator, prefix=prefix)
                return status, response

            status, _, body = await request("GET", "", headers=admin, prefix="conversations", query=b"queue=assigned")
            assert status == 200
            conversation_id = json.loads(body)[0]["id"]
            target = json.loads((await call("conversations", "GET", "operators"))[1])
            operator_id = next(user["id"] for user in target if user["name"] == "Primeiro")
            assert (await call("conversations", "POST", f"{conversation_id}/transfer", {"user_id": operator_id}))[0] == 204
            outgoing = {"request_id": str(uuid4()), "text": "Olá, aqui é a Nexus."}
            for _ in range(2):
                assert (await call("conversations", "POST", f"{conversation_id}/messages", outgoing, admin_only=False))[0] == 202
            assert (await call("conversations", "POST", f"{conversation_id}/messages", outgoing))[0] == 409

            with patch("src.services.openai.request_json", return_value=vector):
                assert (await call("knowledge", "PUT", "", {"source": "Expediente", "text": "Atendemos em horário comercial."}))[0] == 200
                status, imported = await call("knowledge", "PUT", "", {"source": "Cópia", "text": "Atendemos em horário comercial."})
                assert status == 200 and json.loads(imported)["source"] == "Expediente"
            assert json.loads((await call("knowledge", "GET", ""))[1]) == [{"source": "Expediente", "chunks": 1}]
            assert (await call("knowledge", "GET", "", admin_only=False))[0] == 403
            assert (await call("knowledge", "PUT", "welcome", {"message": "Bem-vindo à Nexus!"}, admin_only=False))[0] == 403
            assert (await call("knowledge", "PUT", "welcome", {"message": " Bem-vindo à Nexus! "}))[0] == 200
            assert json.loads((await call("knowledge", "GET", "welcome"))[1])["message"] == "Bem-vindo à Nexus!"
            assert (await call("knowledge", "POST", "preview", {"question": "Qual é o expediente?"}, admin_only=False))[0] == 403
            with patch("src.services.openai.request_json", side_effect=[vector, completion]):
                status, preview = await call("knowledge", "POST", "preview", {"question": "Qual é o expediente?"})
            assert status == 200 and json.loads(preview) == {
                "status": "answered", "message": "Bem-vindo à Nexus!\n\nAtendemos em horário comercial.",
                "sources": ["Expediente"],
            }
            status, preview = await call("knowledge", "POST", "preview", {"question": "Quero um atendente"})
            assert status == 200 and json.loads(preview)["status"] == "handoff"
            with patch("src.services.openai.request_json", side_effect=[vector, completion]):
                status, preview = await call("knowledge", "POST", "preview", {"question": "Qual o horário do atendimento humano?"})
            assert status == 200 and json.loads(preview)["status"] == "answered"

            async def receive(message_id: str, content: str, phone: str = "5511888888888") -> None:
                raw = json.dumps({"event": "message.received", "sessionId": SESSION, "data": {
                    "id": message_id, "from": f"{phone}@c.us", "fromMe": False, "body": content,
                }}).encode()
                signature = b"sha256=" + digest(SECRET.encode(), raw, "sha256").hex().encode()
                assert (await request("POST", str(TENANT), raw, ((b"x-openwa-signature", signature),), prefix="webhooks/openwa"))[0] == 204

            async def drain() -> None:
                for _ in range(10):
                    if not await worker.run_once():
                        break

            for message_id, content in (("work-ai", "Qual é o expediente?"), ("work-name", "Meu nome é Ana Souza"),
                                        ("work-human", "Quero falar com um atendente"), ("work-invalid-category", "9"),
                                        ("work-category", "3")):
                await receive(message_id, content)
                with (patch("src.services.openwa.request_json", side_effect=lambda *_args: {"data": {"messageId": str(uuid4())}}) as whatsapp,
                      patch("src.services.resend.request_json", return_value={"id": "email-id"}) as resend,
                      patch("src.services.openai.request_json", side_effect=[vector, completion]) as ai):
                    await drain()
                    if message_id == "work-ai":
                        assert whatsapp.call_count == 2 and ai.call_count == 0 and resend.call_count == 2
                        direct, = [args.args[2] for args in resend.call_args_list if "transferida" in args.args[2]["subject"]]
                        assert direct["to"] == ["first@example.test"]
                        assert whatsapp.call_args.args[2]["text"] == "Bem-vindo à Nexus!\n\nComo posso chamar você?"
                    elif message_id == "work-name":
                        assert whatsapp.call_count == 1 and ai.call_count == 2 and resend.call_count == 0
                        assert whatsapp.call_args.args[2]["text"] == "Prazer, Ana Souza!\n\nAtendemos em horário comercial."
                        assert "Qual é o expediente?" in str(ai.call_args.args[2])
                        continue
                    elif message_id in {"work-human", "work-invalid-category"}:
                        assert whatsapp.call_count == 1 and ai.call_count == 0 and resend.call_count == 0
                        assert "1. Comercial\n2. Financeiro\n3. Suporte\n4. SAC" in whatsapp.call_args.args[2]["text"]
                        continue
                    else:
                        assert whatsapp.call_count == 1 and ai.call_count == 0 and resend.call_count == 1
                        assert not whatsapp.call_args.args[2]["text"].startswith("Bem-vindo")
                    for email in resend.call_args_list:
                        email_headers = email.args[1]
                        assert email_headers["Idempotency-Key"].startswith("nexus-atende/handoff/")
                        assert "5511888888888" not in str(email.args[2])

            status, body = await call("conversations", "GET", f"{conversation_id}/messages")
            assert status == 200 and sum(row["id"] == outgoing["request_id"] and row["delivery_status"] == "sent"
                                         for row in json.loads(body)) == 1
            status, body = await call("conversations", "GET", "")
            assert status == 200 and json.loads(body)[0]["chat_id"] == "5511888888888@c.us"
            assert json.loads(body)[0]["customer_name"] == "Ana Souza"
            bot_id = json.loads(body)[0]["id"]
            assert json.loads(body)[0]["department"] == "suporte"
            assert json.loads((await call("conversations", "GET", "", admin_only=False))[1]) == []
            assert (await call("conversations", "POST", f"{bot_id}/claim", admin_only=False))[0] == 409
            second_id = next(user["id"] for user in target if user["name"] == "Segundo")
            assert (await call("operators", "PUT", second_id, {"name": "Segundo", "is_active": True, "department": "suporte"}))[0] == 200
            _, support = await login(b"SECOND@EXAMPLE.TEST")
            support_queue = (await request("GET", "", headers=support, prefix="conversations"))[2]
            assert json.loads(support_queue)[0]["id"] == bot_id
            async with EventRepository(engine).listen(TENANT) as changed:
                assert (await call("conversations", "PUT", f"{bot_id}/bot", {"active": True}))[0] == 204
                await asyncio.wait_for(changed.wait(), timeout=2)
            async with tenant_transaction(engine, TENANT) as connection:
                await connection.execute(text("""
                    UPDATE nexus_atende.messages SET created_at = created_at - interval '20 minutes'
                    WHERE conversation_id = CAST(:id AS uuid)
                """), {"id": bot_id})
            returning = json.dumps({"event": "message.received", "sessionId": SESSION, "data": {
                "id": "work-return", "from": "5511888888888@c.us", "fromMe": False, "body": "Qual o horário?",
            }}).encode()
            signature = b"sha256=" + digest(SECRET.encode(), returning, "sha256").hex().encode()
            assert (await request("POST", str(TENANT), returning, ((b"x-openwa-signature", signature),), prefix="webhooks/openwa"))[0] == 204
            recap = {"choices": [{"message": {"content": "Cliente perguntou sobre o expediente."}}]}
            with patch("src.services.openai.request_json", side_effect=[recap, vector, completion]) as ai:
                while ai.call_count == 0:
                    assert await worker.run_once()
                assert ai.call_count == 3
            async with tenant_transaction(engine, TENANT) as connection:
                summary = await connection.scalar(text("""
                    SELECT previous_summary FROM nexus_atende.customers WHERE chat_id = '5511888888888@c.us'
                """))
                assert summary == "Cliente perguntou sobre o expediente."

            origin = {"name": "RotaFY", "slug": "rotafy"}
            assert (await call("knowledge", "PUT", "origins", origin, admin_only=False))[0] == 403
            assert (await call("knowledge", "PUT", "origins", origin))[0] == 200
            assert json.loads((await call("knowledge", "GET", "origins"))[1]) == [origin]
            with patch("src.services.openwa.request_json", side_effect=lambda *_args: {"data": {"messageId": str(uuid4())}}) as whatsapp:
                await drain()
                assert (await call("conversations", "POST", f"{bot_id}/close", admin_only=False))[0] == 409
                assert (await call("conversations", "POST", f"{bot_id}/close"))[0] == 204
                await receive("work-reopen", "Olá, tudo bem?")
                async with tenant_transaction(engine, TENANT) as connection:
                    await connection.execute(text("""
                        UPDATE nexus_atende.messages SET created_at = '2026-11-20 17:00:00+00'
                        WHERE openwa_message_id = 'work-reopen'
                    """))
                await drain()
                assert whatsapp.call_args.args[2]["text"] == "Bem-vindo à Nexus!\n\nBoa tarde, Ana Souza!\n\nComo posso ajudar?"
                assert (await call("conversations", "POST", f"{bot_id}/close"))[0] == 204
                marker = "Olá, vim pelo RotaFY. [Nexus:rotafy]"
                await receive("work-known-origin", marker)
                await drain()
                assert whatsapp.call_args.args[2]["text"] == "Como posso ajudar?"
                await receive("work-new-origin", f"{marker}\nQual é o expediente?", "5511777777777")
                await drain()
                assert whatsapp.call_args.args[2]["text"] == "Como posso chamar você?"
                await receive("work-new-name", "João", "5511777777777")
                with patch("src.services.openai.request_json", side_effect=[vector, completion]) as ai:
                    await drain()
                assert "RotaFY: Qual é o expediente?" in str(ai.call_args_list[0].args[2])
                assert whatsapp.call_args.args[2]["text"] == "Prazer, João!\n\nAtendemos em horário comercial."
            status, _, sourced = await request("GET", "", headers=admin, prefix="conversations", query=b"queue=bot")
            assert status == 200 and next(row for row in json.loads(sourced) if row["id"] == bot_id)["origin_name"] == "RotaFY"

            markdown = "# Configuração\n\n- Acesse **WhatsApp** no painel."
            with patch("src.services.openai.request_json", return_value=vector):
                for kind, document in (("txt", b"Nexus"), ("md", markdown.encode("utf-8-sig")), ("docx", sample_docx()), ("pdf", sample_pdf())):
                    status, _, body = await request("PUT", "file", document, admin, prefix="knowledge",
                                                    query=f"kind={kind}&source={kind}".encode())
                    assert status == 200, (kind, status, body)
                assert (await call("knowledge", "PUT", "url", {"source": "Web", "url": "https://other.test/"}))[0] == 422
            async with tenant_transaction(engine, TENANT) as connection:
                assert await connection.scalar(text("SELECT content FROM nexus_atende.knowledge_chunks WHERE source = 'md'")) == markdown
            with patch("src.services.openai.request_json") as embeddings:
                status, _, too_long = await request("PUT", "file", sample_pdf(b"A" * 40_001), admin,
                                                    prefix="knowledge", query=b"kind=pdf&source=Manual")
                assert status == 422 and "mais de 40.000 caracteres" in json.loads(too_long)["detail"]
                embeddings.assert_not_called()
            status, users = await call("operators", "GET", "")
            assert status == 200 and len(json.loads(users)) == 2
            status, settings_view = await call("integrations", "PUT", "resend", {
                "sender": "from@example.test", "recipient": "test-recipient@example.test", "api_key": "resend-test-secret",
            })
            assert status == 200 and b"resend-test-secret" not in settings_view
            with patch("src.services.resend.request_json", return_value={"id": "resend-test-id"}) as test_email:
                assert (await call("integrations", "POST", "resend/test"))[0] == 204
                assert test_email.call_args.args[2]["to"] == ["test-recipient@example.test"]
            rejected = HTTPError("https://api.resend.com/emails", 403, "test", hdrs=Message(), fp=None)
            with patch("src.services.resend.request_json", side_effect=rejected):
                status, failure = await call("integrations", "POST", "resend/test")
                assert status == 424 and b"403" in failure
            with patch("src.services.resend.request_json", side_effect=TimeoutError):
                status, failure = await call("integrations", "POST", "resend/test")
                assert status == 424 and b"api.resend.com" in failure
            assert (await call("integrations", "GET", "", admin_only=False))[0] == 403
            assert (await call("integrations", "PUT", "openwa", {"api_key": "openwa-test-secret"}))[0] == 200
            endpoint = "https://secondary-openwa.example.test/api"
            assert (await call("integrations", "PUT", "openwa", {"base_url": endpoint}))[0] == 422
            assert (await call("integrations", "PUT", "openwa", {"base_url": "https://unknown.example.test/api", "api_key": "openwa-test-secret"}))[0] == 422
            status, updated = await call("integrations", "PUT", "openwa", {"base_url": f"{endpoint}/", "api_key": "openwa-test-secret"})
            assert status == 200 and json.loads(updated)["openwa_url"] == endpoint
            assert (await call("integrations", "PUT", "openwa", {"base_url": endpoint}))[0] == 200
            number = {"phone_number": "+55 (11) 99999-9999"}
            assert (await call("whatsapp", "PUT", "connection/phone", number, admin_only=False))[0] == 403
            assert (await call("whatsapp", "PUT", "connection/phone", {"phone_number": "123"}))[0] == 422
            status, saved_phone = await call("whatsapp", "PUT", "connection/phone", number)
            assert status == 200 and json.loads(saved_phone)["phone_number"] == "+5511999999999"
            with patch("src.services.openwa.request_json", return_value={"status": "READY"}) as gateway:
                status, connection_body = await call("whatsapp", "GET", "connection")
                assert status == 200 and json.loads(connection_body)["phone_number"] == "+5511999999999"
                assert gateway.call_args.args[0] == f"{endpoint}/sessions/{SESSION}"
            callback = f"https://nexus.example.test/api/v1/webhooks/openwa/{TENANT}"
            active_hook = {"url": callback, "events": ["message.received"], "active": True}
            ready_session = {"status": "READY", "phone": "5511999999999"}
            with patch("src.services.openwa.request_json", side_effect=[ready_session, {"data": []}, {"data": {"id": "hook"}}, ready_session, {"data": {"webhooks": [active_hook]}}]) as hooks:
                await worker.sync_webhook()
                await worker.sync_webhook()
            assert hooks.call_count == 5
            assert hooks.call_args_list[1].args[0] == f"{endpoint}/sessions/{SESSION}/webhooks?limit=100"
            assert hooks.call_args_list[2].args == (f"{endpoint}/sessions/{SESSION}/webhooks", {"X-API-Key": "openwa-test-secret"},
                                                      {"url": callback, "events": ["message.received"], "secret": SECRET})
            status, active = await call("integrations", "GET", "")
            assert status == 200 and json.loads(active)["openwa_webhook_status"] == "active"
            with patch("src.services.openwa.request_json", side_effect=[ready_session, {"data": [{**active_hook, "active": False}]}]) as inactive:
                await worker.sync_webhook()
            assert inactive.call_count == 2
            status, failed = await call("integrations", "GET", "")
            assert status == 200 and json.loads(failed)["openwa_webhook_status"] == "error"
            assert "inativo" in json.loads(failed)["openwa_webhook_error"]
            denied = HTTPError(f"{endpoint}/sessions/{SESSION}", 403, "Forbidden", Message(), None)
            with patch("src.services.openwa.request_json", side_effect=denied):
                status, unavailable = await call("whatsapp", "GET", "connection")
            assert status == 200 and json.loads(unavailable)["session_id"] == str(SESSION)
            assert json.loads(unavailable)["status"] == "UNAVAILABLE" and b"HTTP 403" in unavailable
            async with tenant_transaction(engine, TENANT) as connection:
                encrypted = await connection.scalar(text("SELECT config::text FROM nexus_atende.integrations"))
                assert "resend-test-secret" not in encrypted and "openwa-test-secret" not in encrypted
            with patch("src.services.resend.request_json", return_value={"id": "invite-email"}) as email:
                status, created = await call("operators", "POST", "", {"name": "Terceiro", "email": "third@example.test"})
                member = json.loads(created)
                assert status == 201 and member["invite_sent"] and not member["is_active"], (status, created)
                original = email.call_args.args[2]["text"].split("#")[-1]
            testing_only = HTTPError("https://api.resend.com/emails", 403, "Forbidden", Message(),
                                     BytesIO(b'{"message":"You can only send testing emails to private@example.test"}'))
            with patch("src.services.resend.request_json", side_effect=testing_only):
                status, invite_response = await call("operators", "POST", f"{member['id']}/invite")
            failed_invite = json.loads(invite_response)
            assert status == 200 and failed_invite["invite_pending"] and not failed_invite["invite_sent"]
            assert "HTTP 403" in failed_invite["invite_error"] and "domínio verificado" in failed_invite["invite_error"]
            assert b"private@example.test" not in invite_response
            with patch("src.services.resend.request_json", return_value={"id": "renewed-email"}) as email:
                assert (await call("operators", "POST", f"{member['id']}/invite"))[0] == 200
                renewed = email.call_args.args[2]["text"].split("#")[-1]
            assert (await call("operators", "POST", "accept-invite", {"token": original, "password": "test-password-123"}))[0] == 400
            assert (await call("operators", "POST", "accept-invite", {"token": renewed, "password": "test-password-123"}))[0] == 204
            assert (await call("operators", "POST", "accept-invite", {"token": renewed, "password": "test-password-123"}))[0] == 400
            _, third = await login(b"third@example.test")
            assert (await call("operators", "PUT", operator_id, {"name": "Primeiro", "is_active": False}))[0] == 200
            assert (await request("GET", "me", headers=operator))[0] == 401
            assert (await request("GET", "me", headers=third))[0] == 200
            status, waiting = await call("conversations", "GET", "")
            assert status == 200 and conversation_id in {row["id"] for row in json.loads(waiting)}
            assert (await call("integrations", "PUT", "ai", {"provider": "ollama", "model": "test-local"}))[0] == 200
            with patch("src.services.openai.request_json") as local:
                status, body = await call("knowledge", "POST", "preview", {"question": "Qual é o expediente?"})
            assert status == 200 and json.loads(body)["status"] == "unavailable" and b"Reimporte" in body
            local.assert_not_called()
            assert (await call("integrations", "PUT", "ai", {"provider": "gemini", "model": "test-gemini", "api_key": "test-gemini-key"}))[0] == 200
            gemini_vector = {"embeddings": [{"values": [1.0] + [0.0] * 767}]}
            with patch("src.services.openai.request_json", side_effect=[gemini_vector, gemini_vector, completion]) as gemini:
                assert (await call("knowledge", "PUT", "", {"source": "Expediente", "text": "Horário comercial"}))[0] == 200
                status, body = await call("knowledge", "POST", "preview", {"question": "Qual é o expediente?"})
            assert status == 200 and json.loads(body)["status"] == "answered"
            assert gemini.call_args.args[0].endswith("/openai/chat/completions")
            assert (await call("integrations", "PUT", "ai", {"provider": "anthropic", "model": "test-claude", "api_key": "test-claude-key"}))[0] == 200
            claude_answer = {"content": [{"type": "text", "text": '{"needs_human":false,"answer":"Por aqui."}'}]}
            with patch("src.services.openai.request_json", side_effect=[vector, claude_answer]) as claude:
                status, body = await call("knowledge", "POST", "preview", {"question": "Qual é o expediente?"})
            assert status == 200 and json.loads(body)["status"] == "answered"
            assert claude.call_args.args[0] == "https://api.anthropic.com/v1/messages"

            production = Settings(public_origin="https://atende.nexusdataanalytics.tech", openwa_base_url=None, openwa_allowed_urls="")
            production = production.model_copy(update={"openwa_webhook_tenant_id": None})
            known_endpoint = "https://openwa.187-77-58-10.sslip.io/api"
            service = IntegrationService(IntegrationRepository(engine), production)
            saved = await service.save_openwa(OTHER, OpenWASettings(base_url=known_endpoint, api_key=SecretStr("test-only")))
            assert saved.openwa_url == known_endpoint and saved.openwa_has_key
            explicit = production.model_copy(update={"openwa_allowed_urls": "https://custom.example.test/api"})
            assert explicit.openwa_endpoint() is None
            assert production.model_copy(update={"public_origin": "http://127.0.0.1:3000"}).openwa_endpoint() is None

            async with tenant_transaction(engine, TENANT) as connection:
                await connection.execute(text("UPDATE nexus_atende.tenants SET openwa_session_id = NULL, openwa_number_verified = false"))
            with patch("src.services.openwa.request_json", side_effect=[{"data": []}, {"data": {"id": SESSION}}, {"status": "created"}, {"data": {}}]) as pairing:
                assert (await call("whatsapp", "POST", "connection/pair"))[0] == 204
            assert pairing.call_args_list[1].args[2] == {"name": f"nexus-atende-{TENANT}"}
            assert pairing.call_args_list[-1].args[0] == f"{endpoint}/sessions/{SESSION}/start"
            with patch("src.services.openwa.request_json", return_value={"status": "ready", "phone": "5511999990000"}) as wrong_phone:
                await worker.sync_webhook()
                status, wrong_connection = await call("whatsapp", "GET", "connection")
            assert wrong_phone.call_count == 2
            assert status == 200 and json.loads(wrong_connection)["status"] == "WRONG_NUMBER"
            async with tenant_transaction(engine, TENANT) as connection:
                assert await connection.scalar(text("SELECT openwa_number_verified FROM nexus_atende.tenants")) is False

            assert (await request("GET", "", headers=third, prefix="clients"))[0] == 403
            details = {"address": "Rua Teste, 123", "document": "12.345.678/0001-95",
                       "contact_phone": "+5511999990001", "contact_email": "contact@example.test"}
            client_data = {"name": "Cliente Piloto", "details": details, "admin": {"name": "Admin Piloto", "email": "pilot@example.test"}}
            with patch("src.services.resend.request_json", return_value={"id": "client-invite"}) as email:
                status, created_client = await call("clients", "POST", "", client_data)
            assert status == 201, created_client
            assert email.call_args.args[2]["to"] == ["pilot@example.test"]
            assert email.call_args.args[2]["from"] == "from@example.test"
            client_id = json.loads(created_client)["id"]
            assert json.loads(created_client)["details"]["document"] == "12345678000195"
            assert b"contact@example.test" not in (await request("GET", "companies"))[2]
            token = email.call_args.args[2]["text"].split("#")[-1]
            assert (await call("operators", "POST", "accept-invite", {"token": token, "password": "test-password-123"}))[0] == 204
            origin_header = next(header for header in admin if header[0] == b"origin")
            credentials = {"email": "pilot@example.test", "password": "test-password-123"}
            assert (await request("POST", "login", json.dumps(credentials).encode(), (origin_header,)))[0] == 401
            pilot_login = json.dumps({**credentials, "tenant_id": client_id}).encode()
            status, pilot_headers, pilot_body = await request("POST", "login", pilot_login, (origin_header,))
            assert status == 200 and json.loads(pilot_body)["platform_admin"] is False
            pilot_cookies = SimpleCookie()
            for name, value in pilot_headers:
                if name == b"set-cookie":
                    pilot_cookies.load(value.decode())
            pilot = ((b"cookie", f"nexus_atende_session={pilot_cookies['nexus_atende_session'].value}".encode()),
                     (b"x-csrf-token", pilot_cookies["nexus_atende_csrf"].value.encode()), origin_header)
            assert (await request("GET", "handoff-email", headers=third, prefix="integrations"))[0] == 403
            assert json.loads((await request("GET", "handoff-email", headers=pilot, prefix="integrations"))[2]) == {"email": ""}
            assert (await request("PUT", "handoff-email", b'{"email":"support@pilot.test"}', pilot, prefix="integrations"))[0] == 200
            assert json.loads((await call("integrations", "GET", "handoff-email"))[1]) == {"email": "to@example.test"}
            pilot_resend = await IntegrationService(IntegrationRepository(engine), Settings()).resend(UUID(client_id))
            assert pilot_resend is not None
            with patch("src.services.resend.request_json", return_value={"id": "pilot-alert"}) as pilot_email:
                await pilot_resend.send_test()
            assert pilot_email.call_args.args[2]["to"] == ["support@pilot.test"]
            assert (await request("GET", "", headers=pilot, prefix="clients"))[0] == 403
            assert (await request("PUT", "ai", b'{"provider":"openai","model":"test"}', pilot, prefix="integrations"))[0] == 403
            assert (await request("GET", "", headers=pilot, prefix="integrations"))[0] == 403
            assert (await request("PUT", "openwa", b'{"api_key":"different-key"}', pilot, prefix="integrations"))[0] == 403
            assert (await request("GET", "connection", headers=pilot, prefix="whatsapp"))[0] == 200
            pilot_tenant = UUID(client_id)
            pilot_session = uuid4()
            async with tenant_transaction(engine, pilot_tenant) as connection:
                await connection.execute(text("""
                    UPDATE nexus_atende.tenants SET openwa_session_id = :session, openwa_number_verified = true
                    WHERE id = :tenant
                """), {"session": pilot_session, "tenant": pilot_tenant})
            with patch("src.services.openwa.request_json", return_value={"status": "READY"}) as shared_gateway:
                status, _, connected_pilot = await request("GET", "connection", headers=pilot, prefix="whatsapp")
            assert status == 200 and json.loads(connected_pilot)["status"] == "READY"
            assert shared_gateway.call_args.args[:2] == (f"{endpoint}/sessions/{pilot_session}", {"X-API-Key": "openwa-test-secret"})
            pilot_event = json.dumps({"event": "message.received", "sessionId": str(pilot_session), "data": {
                "id": "pilot-message", "from": "5511888888888@c.us", "fromMe": False, "body": "Olá",
            }}).encode()
            key = tenant_webhook_secret(TENANT, pilot_tenant, SecretStr(SECRET)).get_secret_value()
            pilot_signature = (b"x-openwa-signature", b"sha256=" + digest(key.encode(), pilot_event, "sha256").hex().encode())
            assert (await request("POST", client_id, pilot_event, (pilot_signature,), prefix="webhooks/openwa"))[0] == 204
            ar = b'{"email":"admin@example.test","password":"test-password-123"}'
            status, _, platform = await request("POST", "login", ar, (origin_header,))
            assert status == 200 and json.loads(platform)["platform_admin"] is True
            assert (await call("clients", "DELETE", str(TENANT)))[0] == 422
            assert (await call("clients", "PUT", client_id, {"name": "Piloto atualizado", "details": {**details, "address": "Rua Nova, 321"}}))[0] == 204
            assert (await call("clients", "DELETE", client_id))[0] == 204
            assert (await request("GET", "me", headers=pilot))[0] == 401
            assert (await request("POST", "login", pilot_login, (origin_header,)))[0] == 401
            assert client_id.encode() not in (await request("GET", "companies"))[2]
            archived = next(row for row in json.loads((await call("clients", "GET", ""))[1]) if row["id"] == client_id)
            assert archived["archived_at"] and archived["name"] == "Piloto atualizado"
            assert archived["details"]["address"] == "Rua Nova, 321"
            async with tenant_transaction(engine, pilot_tenant) as connection:
                assert await connection.scalar(text("SELECT count(*) FROM nexus_atende.messages")) == 1
                assert await connection.scalar(text("SELECT status FROM nexus_atende.work_items")) == "cancelled"

            retry_headers = Message()
            retry_headers["Retry-After"] = "90"
            limited = HTTPError(f"{endpoint}/sessions/{SESSION}", 429, "Rate limited", retry_headers, None)
            with (patch("src.services.openwa.monotonic", return_value=1000) as clock,
                  patch("src.services.openwa.time", side_effect=lambda: clock.return_value),
                  patch("src.services.openwa.request_json", side_effect=[limited, ready_session, {"data": [active_hook]}]) as gateway):
                await worker.sync_webhook()
                status, gateway_state = await call("integrations", "GET", "")
                assert status == 200 and json.loads(gateway_state)["openwa_webhook_status"] == "rate_limited"
                with patch("src.services.openwa.OpenWAClient._cooldown", {}):
                    status, deferred = await call("whatsapp", "GET", "connection")
                deferred_session = json.loads(deferred)
                assert status == 200 and deferred_session["status"] == "RATE_LIMITED"
                assert deferred_session["session_id"] == str(SESSION) and deferred_session["retry_after"] == 90
                await worker.sync_webhook()
                assert gateway.call_count == 1
                clock.return_value = 1091
                await worker.sync_webhook()
                assert gateway.call_count == 3
                status, recovered = await call("integrations", "GET", "")
                assert status == 200 and json.loads(recovered)["openwa_webhook_status"] == "active"

            conversation = UUID(bot_id)
            assert (await call("integrations", "PUT", "handoff-email", {"email": ""}))[0] == 200
            async with tenant_transaction(engine, TENANT) as connection:
                for answer in ("Primeira resposta", "Segunda resposta"):
                    outgoing_id = await connection.scalar(text("""
                        INSERT INTO nexus_atende.messages (tenant_id, conversation_id, sender_type, content)
                        VALUES (:tenant, :conversation, 'bot', :answer) RETURNING id
                    """), {"tenant": TENANT, "conversation": conversation, "answer": answer})
                    await enqueue(connection, TENANT, conversation, "whatsapp", outgoing_id)
            limited_send = HTTPError(f"{endpoint}/sessions/{SESSION}/messages/send-text", 429, "Rate limited", retry_headers, None)
            with (patch("src.services.openwa.monotonic", return_value=1200) as clock,
                  patch("src.services.openwa.time", side_effect=lambda: clock.return_value),
                  patch("src.services.openwa.request_json", side_effect=[
                      limited_send, {"data": {"messageId": str(uuid4())}}, {"data": {"messageId": str(uuid4())}},
                  ]) as delivery):
                assert await worker.run_once()
                assert not await worker.run_once()
                async with tenant_transaction(engine, TENANT) as connection:
                    pending = await connection.execute(text("""
                        SELECT status, extract(epoch FROM available_at - now()) AS seconds FROM nexus_atende.work_items
                        WHERE kind = 'whatsapp' AND status = 'pending' ORDER BY created_at
                    """))
                    items = pending.all()
                    assert len(items) == 2 and 85 <= items[0].seconds <= 90
                    await connection.execute(text("""
                        UPDATE nexus_atende.work_items SET available_at = now() WHERE kind = 'whatsapp' AND status = 'pending'
                    """))
                clock.return_value = 1291
                await drain()
                assert [call.args[2]["text"] for call in delivery.call_args_list] == [
                    "Primeira resposta", "Primeira resposta", "Segunda resposta",
                ]
            assert (await call("operators", "DELETE", member["id"]))[0] == 204
            assert (await request("GET", "me", headers=third))[0] == 401
            assert member["id"].encode() not in (await call("operators", "GET", ""))[1]
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(check())
