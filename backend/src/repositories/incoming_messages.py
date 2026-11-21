from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from src.repositories.database import tenant_transaction
from src.repositories.work import enqueue
from src.schemas.openwa_events import IncomingText


class IncomingMessageRepository:
    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def save(self, tenant_id: UUID, message: IncomingText, *, bot_enabled: bool = False, activity_only: bool = False) -> None:
        async with tenant_transaction(self._engine, tenant_id) as connection:
            binding = await connection.scalar(text("""
                SELECT 1 FROM nexus_atende.tenants WHERE id = :tenant_id AND openwa_session_id = :session_id
                    AND openwa_number_verified AND archived_at IS NULL FOR SHARE
            """), {"tenant_id": tenant_id, "session_id": message.session_id})
            if binding is None:
                return
            await connection.execute(
                text("SELECT pg_advisory_xact_lock(hashtextextended(:event_key, 0))"),
                {"event_key": f"openwa:{tenant_id}:{message.session_id}:{message.message_id}"},
            )
            duplicate = await connection.scalar(text("""
                SELECT 1 FROM nexus_atende.messages WHERE tenant_id = :tenant_id
                    AND openwa_session_id = :session_id AND openwa_message_id = :message_id
            """), {"tenant_id": tenant_id, "session_id": message.session_id, "message_id": message.message_id})
            if duplicate is not None:
                return

            await connection.execute(text("""
                INSERT INTO nexus_atende.customers (tenant_id, chat_id) VALUES (:tenant_id, :chat_id)
                ON CONFLICT (tenant_id, chat_id) DO NOTHING
            """), {"tenant_id": tenant_id, "chat_id": message.chat_id})
            customer_id = await connection.scalar(text("""
                SELECT id FROM nexus_atende.customers WHERE tenant_id = :tenant_id AND chat_id = :chat_id
            """), {"tenant_id": tenant_id, "chat_id": message.chat_id})
            new_conversation = await connection.scalar(text("""
                INSERT INTO nexus_atende.conversations (tenant_id, customer_id, state, opening_pending)
                VALUES (:tenant_id, :customer_id, :state, true)
                ON CONFLICT (tenant_id, customer_id) DO NOTHING RETURNING id
            """), {"tenant_id": tenant_id, "customer_id": customer_id, "state": "bot" if bot_enabled else "waiting"})
            result = await connection.execute(text("""
                SELECT id, state FROM nexus_atende.conversations
                WHERE tenant_id = :tenant_id AND customer_id = :customer_id FOR UPDATE
            """), {"tenant_id": tenant_id, "customer_id": customer_id})
            conversation_id, state = result.one()
            inserted = await connection.scalar(text("""
                INSERT INTO nexus_atende.messages
                    (tenant_id, conversation_id, sender_type, openwa_session_id, openwa_message_id, content, created_at)
                VALUES (:tenant_id, :conversation_id, 'customer', :session_id, :message_id, :content, clock_timestamp())
                ON CONFLICT (tenant_id, openwa_session_id, openwa_message_id) DO NOTHING
                RETURNING id
            """), {
                "tenant_id": tenant_id, "conversation_id": conversation_id, "session_id": message.session_id,
                "message_id": message.message_id, "content": message.content,
            })
            if inserted is not None:
                await connection.execute(text("""
                    UPDATE nexus_atende.customers
                    SET last_seen_at = greatest(last_seen_at, now()), total_interactions = total_interactions + 1
                    WHERE tenant_id = :tenant_id AND id = :customer_id
                """), {"tenant_id": tenant_id, "customer_id": customer_id})
                reopened = state == "closed"
                if reopened:
                    state = "bot" if bot_enabled else "waiting"
                await connection.execute(text("""
                    UPDATE nexus_atende.conversations
                    SET last_interaction = greatest(last_interaction, now()), state = :state,
                        inactivity_due_at = NULL, inactivity_notice_id = NULL
                    WHERE tenant_id = :tenant_id AND id = :conversation_id
                """), {"tenant_id": tenant_id, "conversation_id": conversation_id, "state": state})
                await connection.execute(text("""
                    UPDATE nexus_atende.work_items SET status = 'cancelled'
                    WHERE tenant_id = :tenant_id AND conversation_id = :conversation_id AND inactivity_notice
                        AND status IN ('pending', 'processing')
                """), {"tenant_id": tenant_id, "conversation_id": conversation_id})
                if state == "bot" and not activity_only:
                    await enqueue(connection, tenant_id, conversation_id, "rag", inserted)
                elif new_conversation is not None or reopened:
                    await enqueue(connection, tenant_id, conversation_id, "notify")
