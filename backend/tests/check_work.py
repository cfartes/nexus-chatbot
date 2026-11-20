import asyncio
import json
import os
from hmac import digest
from io import BytesIO
from unittest.mock import patch
from uuid import uuid4
from zipfile import ZipFile

from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from src.main import app
from src.repositories.database import tenant_transaction
from src.repositories.events import EventRepository
from src.settings import Settings
from src.worker import Worker
from tests.check_auth import request
from tests.check_conversations import login
from tests.check_webhook import SECRET, SESSION, TENANT


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
                    else:
                        assert whatsapp.call_count == 1 and ai.call_count == 0 and resend.call_count == 1
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
            status, created = await call("operators", "POST", "", {
                "name": "Terceiro", "email": "third@example.test", "password": "test-password-123",
            })
            assert status == 201, (status, created)
            _, third = await login(b"third@example.test")
            assert (await call("operators", "PUT", operator_id, {"name": "Primeiro", "is_active": False}))[0] == 200
            assert (await request("GET", "me", headers=operator))[0] == 401
            assert (await request("GET", "me", headers=third))[0] == 200
            status, waiting = await call("conversations", "GET", "")
            assert status == 200 and conversation_id in {row["id"] for row in json.loads(waiting)}
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(check())
