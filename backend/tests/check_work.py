import asyncio
import json
import os
from hmac import digest
from io import BytesIO
from unittest.mock import patch
from uuid import uuid4
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
from src.schemas.integrations import OpenWASettings
from src.services.integrations import IntegrationService
from src.settings import Settings
from src.worker import Worker
from tests.check_auth import request
from tests.check_conversations import login
from tests.check_webhook import OTHER, SECRET, SESSION, TENANT


def sample_pdf() -> bytes:
    writer = PdfWriter()
    page = writer.add_blank_page(100, 100)
    page[NameObject("/Resources")] = DictionaryObject({NameObject("/Font"): DictionaryObject({
        NameObject("/F1"): DictionaryObject({NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"), NameObject("/BaseFont"): NameObject("/Helvetica")}),
    })})
    stream = DecodedStreamObject()
    stream.set_data(b"BT /F1 12 Tf 10 20 Td (Nexus em horario comercial) Tj ET")
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

            for message_id, content in (("work-ai", "Qual é o expediente?"), ("work-human", "Quero falar com um atendente")):
                raw = json.dumps({"event": "message.received", "sessionId": SESSION, "data": {
                    "id": message_id, "from": "5511888888888@c.us", "fromMe": False, "body": content,
                }}).encode()
                signature = b"sha256=" + digest(SECRET.encode(), raw, "sha256").hex().encode()
                assert (await request("POST", str(TENANT), raw, ((b"x-openwa-signature", signature),), prefix="webhooks/openwa"))[0] == 204
                with (patch("src.services.openwa.request_json", side_effect=lambda *_args: {"data": {"messageId": str(uuid4())}}) as whatsapp,
                      patch("src.services.resend.request_json", return_value={"id": "email-id"}) as resend,
                      patch("src.services.openai.request_json", side_effect=[vector, completion]) as ai):
                    for _ in range(10):
                        if not await worker.run_once():
                            break
                    if message_id == "work-ai":
                        assert whatsapp.call_count == 2 and ai.call_count == 2 and resend.call_count == 1
                        assert whatsapp.call_args.args[2]["text"] == "Bem-vindo à Nexus!\n\nAtendemos em horário comercial."
                    else:
                        assert whatsapp.call_count == 1 and ai.call_count == 0 and resend.call_count == 1
                        assert not whatsapp.call_args.args[2]["text"].startswith("Bem-vindo")
                    email_headers = resend.call_args.args[1]
                    assert email_headers["Idempotency-Key"].startswith("nexus-atende/handoff/")
                    assert "5511888888888" not in str(resend.call_args.args[2])

            status, body = await call("conversations", "GET", f"{conversation_id}/messages")
            assert status == 200 and sum(row["id"] == outgoing["request_id"] and row["delivery_status"] == "sent"
                                         for row in json.loads(body)) == 1
            status, body = await call("conversations", "GET", "")
            assert status == 200 and json.loads(body)[0]["chat_id"] == "5511888888888@c.us"
            bot_id = json.loads(body)[0]["id"]
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

            with patch("src.services.openai.request_json", return_value=vector):
                for kind, document in (("txt", b"Nexus"), ("docx", sample_docx()), ("pdf", sample_pdf())):
                    status, _, body = await request("PUT", "file", document, admin, prefix="knowledge",
                                                    query=f"kind={kind}&source={kind}".encode())
                    assert status == 200, (kind, status, body)
                assert (await call("knowledge", "PUT", "url", {"source": "Web", "url": "https://other.test/"}))[0] == 422
            status, users = await call("operators", "GET", "")
            assert status == 200 and len(json.loads(users)) == 2
            status, settings_view = await call("integrations", "PUT", "resend", {
                "sender": "from@example.test", "recipient": "to@example.test", "api_key": "resend-test-secret",
            })
            assert status == 200 and b"resend-test-secret" not in settings_view
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
            with patch("src.services.openwa.request_json", side_effect=[{"data": []}, {"data": {"id": "hook"}}, {"data": [active_hook]}]) as hooks:
                await worker.sync_webhook()
                await worker.sync_webhook()
            assert hooks.call_count == 3
            assert hooks.call_args_list[1].args == (f"{endpoint}/sessions/{SESSION}/webhooks", {"X-API-Key": "openwa-test-secret"},
                                                      {"url": callback, "events": ["message.received"], "secret": SECRET})
            status, active = await call("integrations", "GET", "")
            assert status == 200 and json.loads(active)["openwa_webhook_status"] == "active"
            with patch("src.services.openwa.request_json", return_value={"data": [{**active_hook, "active": False}]}) as inactive:
                await worker.sync_webhook()
            assert inactive.call_count == 1
            status, failed = await call("integrations", "GET", "")
            assert status == 200 and json.loads(failed)["openwa_webhook_status"] == "error"
            async with tenant_transaction(engine, TENANT) as connection:
                encrypted = await connection.scalar(text("SELECT config::text FROM nexus_atende.integrations"))
                assert "resend-test-secret" not in encrypted and "openwa-test-secret" not in encrypted
            with patch("src.services.resend.request_json", return_value={"id": "invite-email"}) as email:
                status, created = await call("operators", "POST", "", {"name": "Terceiro", "email": "third@example.test"})
                member = json.loads(created)
                assert status == 201 and member["invite_sent"] and not member["is_active"], (status, created)
                original = email.call_args.args[2]["text"].split("#")[-1]
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
            with patch("src.services.openai.request_json", return_value={"embeddings": [[1.0] + [0.0] * 767]}) as local:
                status, body = await call("knowledge", "POST", "preview", {"question": "Qual é o expediente?"})
            assert status == 200 and json.loads(body)["status"] == "handoff"
            assert local.call_args.args[0] == "http://127.0.0.1:11434/api/embed"
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
            known_endpoint = "https://openwa.187-77-58-10.sslip.io/api"
            service = IntegrationService(IntegrationRepository(engine), production)
            saved = await service.save_openwa(OTHER, OpenWASettings(base_url=known_endpoint, api_key=SecretStr("test-only")))
            assert saved.openwa_url == known_endpoint and saved.openwa_has_key
            explicit = production.model_copy(update={"openwa_allowed_urls": "https://custom.example.test/api"})
            assert explicit.openwa_endpoint() is None
            assert production.model_copy(update={"public_origin": "http://127.0.0.1:3000"}).openwa_endpoint() is None
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(check())
