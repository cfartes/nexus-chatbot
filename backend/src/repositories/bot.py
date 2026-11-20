from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from src.repositories.database import tenant_transaction
from src.repositories.work import enqueue, finish
from src.schemas.auth import Operator
from src.schemas.knowledge import BotContext, OpeningUpdate
from src.schemas.operators import Department
from src.schemas.work import WorkItem


async def _handoff(connection: AsyncConnection, tenant_id: UUID, conversation_id: UUID) -> None:
    await connection.execute(text("""
        UPDATE nexus_atende.conversations SET state = 'waiting', assigned_user_id = NULL, awaiting_department = false
        WHERE tenant_id = :tenant_id AND id = :id
    """), {"tenant_id": tenant_id, "id": conversation_id})
    await enqueue(connection, tenant_id, conversation_id, "notify")


class BotRepository:
    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def context(self, tenant_id: UUID, work: WorkItem) -> BotContext | None:
        async with tenant_transaction(self._engine, tenant_id) as connection:
            values = {"tenant_id": tenant_id, "id": work.conversation_id, "message_id": work.message_id}
            info = await connection.execute(text("""
                SELECT messages.content, customers.name, customers.previous_summary, tenants.welcome_message,
                    conversations.opening_pending, conversations.opening_question, conversations.origin_slug, conversations.awaiting_department,
                    origins.name AS origin_name,
                    extract(hour FROM messages.created_at AT TIME ZONE 'America/Sao_Paulo')::int AS local_hour
                FROM nexus_atende.messages AS messages
                JOIN nexus_atende.conversations AS conversations
                    ON (conversations.tenant_id, conversations.id) = (messages.tenant_id, messages.conversation_id)
                JOIN nexus_atende.customers AS customers
                    ON (customers.tenant_id, customers.id) = (conversations.tenant_id, conversations.customer_id)
                JOIN nexus_atende.tenants AS tenants ON tenants.id = messages.tenant_id
                LEFT JOIN nexus_atende.contact_origins AS origins
                    ON (origins.tenant_id, origins.slug) = (conversations.tenant_id, conversations.origin_slug)
                WHERE messages.tenant_id = :tenant_id AND messages.id = :message_id
                    AND conversations.id = :id AND conversations.state = 'bot'
            """), values)
            row = info.one_or_none()
            if row is None:
                return None
            history = await connection.execute(text("""
                SELECT messages.sender_type || ': ' || left(messages.content, 1500) AS line,
                    messages.created_at >= question.created_at - interval '15 minutes' AS recent
                FROM nexus_atende.messages AS messages
                JOIN nexus_atende.messages AS question ON question.tenant_id = messages.tenant_id
                    AND question.conversation_id = messages.conversation_id AND question.id = :message_id
                LEFT JOIN nexus_atende.work_items AS delivery ON delivery.tenant_id = messages.tenant_id
                    AND delivery.message_id = messages.id AND delivery.kind = 'whatsapp'
                WHERE messages.tenant_id = :tenant_id AND messages.conversation_id = :id
                    AND (messages.created_at, messages.id) < (question.created_at, question.id)
                    AND (delivery.id IS NULL OR delivery.status = 'sent')
                ORDER BY messages.created_at DESC, messages.id DESC LIMIT 12
            """), values)
            entries = list(reversed(history.all()))
            recent = [entry.line for entry in entries if entry.recent]
            return BotContext(question=row.content, name=row.name, previous_summary=row.previous_summary, welcome_message=row.welcome_message,
                              recent=recent, previous=[] if recent else [entry.line for entry in entries],
                              opening_pending=row.opening_pending, opening_question=row.opening_question,
                              origin_slug=row.origin_slug, origin_name=row.origin_name, local_hour=row.local_hour,
                              awaiting_department=row.awaiting_department)

    async def resolve(self, tenant_id: UUID, work: WorkItem, answer: str | None, fallback: str, summary: str | None,
                      opening: OpeningUpdate | None = None, *, ask_department: bool = False,
                      department: Department | None = None) -> None:
        async with tenant_transaction(self._engine, tenant_id) as connection:
            values = {"tenant_id": tenant_id, "id": work.conversation_id}
            state = await connection.scalar(text("""
                SELECT state FROM nexus_atende.conversations WHERE tenant_id = :tenant_id AND id = :id FOR UPDATE
            """), values)
            active = await connection.scalar(text("""
                SELECT id FROM nexus_atende.work_items WHERE tenant_id = :tenant_id AND id = :work_id
                    AND status = 'processing' AND attempts = :attempts FOR UPDATE
            """), {"tenant_id": tenant_id, "work_id": work.id, "attempts": work.attempts})
            if active is None:
                return
            if state != "bot":
                await finish(connection, tenant_id, work.id, "cancelled")
                return
            if ask_department or department is not None:
                await connection.execute(text("""
                    UPDATE nexus_atende.conversations SET department = :department, awaiting_department = :asking
                    WHERE tenant_id = :tenant_id AND id = :id
                """), {**values, "department": department, "asking": ask_department})
            if opening is not None:
                await connection.execute(text("""
                    UPDATE nexus_atende.conversations
                    SET opening_pending = false, opening_question = :question, origin_slug = :origin_slug
                    WHERE tenant_id = :tenant_id AND id = :id
                """), {**values, "question": opening.pending_question, "origin_slug": opening.origin_slug})
            customer_name = opening.customer_name if opening is not None else None
            if summary is not None or customer_name is not None:
                await connection.execute(text("""
                    UPDATE nexus_atende.customers AS customers
                    SET previous_summary = coalesce(:summary, customers.previous_summary),
                        name = coalesce(:customer_name, customers.name)
                    FROM nexus_atende.conversations AS conversations
                    WHERE conversations.tenant_id = :tenant_id AND conversations.id = :id
                        AND (customers.tenant_id, customers.id) = (conversations.tenant_id, conversations.customer_id)
                """), {**values, "summary": summary, "customer_name": customer_name})
            if answer is None:
                await _handoff(connection, tenant_id, work.conversation_id)
                await connection.execute(text("""
                    UPDATE nexus_atende.work_items SET status = 'cancelled'
                    WHERE tenant_id = :tenant_id AND conversation_id = :id AND kind = 'rag' AND status = 'pending'
                """), values)
            message_id = await connection.scalar(text("""
                INSERT INTO nexus_atende.messages (tenant_id, conversation_id, sender_type, content)
                VALUES (:tenant_id, :id, 'bot', :content) RETURNING id
            """), {**values, "content": fallback if answer is None else answer})
            await enqueue(connection, tenant_id, work.conversation_id, "whatsapp", message_id, allow_waiting=answer is None)
            await finish(connection, tenant_id, work.id, "sent")

    async def set_active(self, actor: Operator, conversation_id: UUID, active: bool) -> bool:
        async with tenant_transaction(self._engine, actor.tenant_id) as connection:
            values = {"tenant_id": actor.tenant_id, "id": conversation_id}
            current = await connection.execute(text("""
                SELECT state, assigned_user_id FROM nexus_atende.conversations
                WHERE tenant_id = :tenant_id AND id = :id FOR UPDATE
            """), values)
            row = current.one_or_none()
            if row is None or row.state == "closed" or (actor.role != "admin" and row.assigned_user_id != actor.id):
                return False
            if active and row.state != "bot":
                await connection.execute(text("""
                    UPDATE nexus_atende.conversations SET state = 'bot', assigned_user_id = NULL,
                        department = NULL, awaiting_department = false
                    WHERE tenant_id = :tenant_id AND id = :id
                """), values)
            elif not active and row.state == "bot":
                await _handoff(connection, actor.tenant_id, conversation_id)
                await connection.execute(text("""
                    UPDATE nexus_atende.work_items AS work SET status = 'cancelled'
                    WHERE tenant_id = :tenant_id AND conversation_id = :id AND status IN ('pending', 'processing')
                        AND (kind = 'rag' OR kind = 'whatsapp' AND EXISTS (
                            SELECT 1 FROM nexus_atende.messages WHERE tenant_id = work.tenant_id
                                AND id = work.message_id AND sender_type = 'bot'
                        ))
                """), values)
            return True
