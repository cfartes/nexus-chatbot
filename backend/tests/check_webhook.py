import asyncio
import json
import os
from hmac import digest
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from src.main import app
from src.repositories.database import tenant_transaction
from tests.check_auth import request

TENANT = UUID("00000000-0000-0000-0000-000000000001")
OTHER = UUID("00000000-0000-0000-0000-000000000002")
SESSION = "00000000-0000-0000-0000-000000000003"
SECRET = "test-only-webhook-signing-secret-000000"


async def check() -> None:
    os.environ["NEXUS_ATENDE_OPENWA_WEBHOOK_TENANT_ID"] = str(TENANT)
    os.environ["NEXUS_ATENDE_OPENWA_WEBHOOK_SECRET"] = SECRET
    raw = json.dumps({"event": "message.received", "sessionId": SESSION, "data": {
        "from": "5511999999999@s.whatsapp.net", "fromMe": False, "id": "msg-1", "body": "Olá",
    }}).encode()

    async def post(body: bytes, tenant: UUID = TENANT, *, signed: bool = True) -> int:
        signature = b"sha256=" + digest(SECRET.encode(), body, "sha256").hex().encode() if signed else b"invalid"
        status, _, _ = await request(
            "POST", str(tenant), body, ((b"x-openwa-signature", signature),), prefix="webhooks/openwa",
        )
        return status

    async with app.router.lifespan_context(app):
        assert await post(raw, signed=False) == 403
        assert await post(raw, OTHER) == 403
        assert await post(b"{") == 400
        assert await post(b"a" * (512 * 1024 + 1), signed=False) == 413
        assert await post(raw.replace(SESSION.encode(), str(OTHER).encode())) == 204
        assert await post(raw.replace(b"@s.whatsapp.net", b"@g.us")) == 204
        first, second = await asyncio.gather(post(raw), post(raw))
        assert first == second == 204
        assert await post(raw.replace(b"5511999999999", b"5511888888888")) == 204
        assert await post(raw.replace(b"msg-1", b"msg-2")) == 204

    engine = create_async_engine(os.environ["NEXUS_ATENDE_DATABASE_URL"])
    try:
        async with tenant_transaction(engine, TENANT) as connection:
            chats = await connection.scalars(text("SELECT chat_id FROM nexus_atende.customers"))
            assert chats.all() == ["5511999999999@c.us"]
            conversations = await connection.scalars(text("SELECT state FROM nexus_atende.conversations"))
            assert conversations.all() == ["waiting"]
            messages = await connection.execute(text("""
                SELECT openwa_message_id, content FROM nexus_atende.messages ORDER BY openwa_message_id
            """))
            assert messages.all() == [("msg-1", "Olá"), ("msg-2", "Olá")]
        async with tenant_transaction(engine, OTHER) as connection:
            assert await connection.scalar(text("SELECT count(*) FROM nexus_atende.messages")) == 0
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(check())
