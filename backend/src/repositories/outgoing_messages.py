from collections.abc import Awaitable, Callable
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from src.repositories.database import tenant_transaction
from src.repositories.work import enqueue, finish
from src.schemas.auth import Operator
from src.schemas.work import WhatsAppDispatch, WorkItem, WorkReceipt, WorkStatus


class OutgoingMessageRepository:
    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def submit(self, actor: Operator, conversation_id: UUID, request_id: UUID, content: str) -> WorkReceipt | None:
        values = {"tenant_id": actor.tenant_id, "conversation_id": conversation_id, "id": request_id,
                  "user_id": actor.id, "content": content}
        async with tenant_transaction(self._engine, actor.tenant_id) as connection:
            assigned = await connection.scalar(text("""
                SELECT id FROM nexus_atende.conversations WHERE tenant_id = :tenant_id
                    AND id = :conversation_id AND state = 'assigned' AND assigned_user_id = :user_id FOR UPDATE
            """), values)
            if assigned is None:
                return None
            inserted = await connection.scalar(text("""
                INSERT INTO nexus_atende.messages (tenant_id, id, conversation_id, sender_type, sender_id, content)
                VALUES (:tenant_id, :id, :conversation_id, 'operator', :user_id, :content)
                ON CONFLICT (tenant_id, id) DO NOTHING RETURNING id
            """), values)
            if inserted is not None:
                await enqueue(connection, actor.tenant_id, conversation_id, "whatsapp", request_id)
            status = await connection.scalar(text("""
                SELECT work.status FROM nexus_atende.work_items AS work JOIN nexus_atende.messages AS messages
                    ON (work.tenant_id, work.message_id) = (messages.tenant_id, messages.id)
                WHERE work.tenant_id = :tenant_id AND work.kind = 'whatsapp' AND messages.id = :id
                    AND messages.conversation_id = :conversation_id AND messages.sender_id = :user_id
                    AND messages.content = :content
            """), values)
            return WorkReceipt(id=request_id, status=status) if status is not None else None

    async def dispatch(
        self, tenant_id: UUID, work: WorkItem,
        send: Callable[[UUID, str, str], Awaitable[WhatsAppDispatch]],
    ) -> None:
        async with tenant_transaction(self._engine, tenant_id) as connection:
            result = await connection.execute(text("""
                SELECT conversations.state, conversations.assigned_user_id, customers.chat_id,
                    tenants.openwa_session_id, tenants.openwa_number_verified, messages.sender_type, messages.sender_id, messages.content
                FROM nexus_atende.conversations AS conversations
                JOIN nexus_atende.customers AS customers
                    ON (customers.tenant_id, customers.id) = (conversations.tenant_id, conversations.customer_id)
                JOIN nexus_atende.tenants AS tenants ON tenants.id = conversations.tenant_id
                JOIN nexus_atende.messages AS messages
                    ON (messages.tenant_id, messages.conversation_id) = (conversations.tenant_id, conversations.id)
                WHERE conversations.tenant_id = :tenant_id AND conversations.id = :conversation_id
                    AND messages.id = :message_id FOR UPDATE OF conversations
            """), {"tenant_id": tenant_id, "conversation_id": work.conversation_id, "message_id": work.message_id})
            row = result.mappings().one_or_none()
            reservation = await connection.execute(text("""
                SELECT allow_waiting, openwa_session_id FROM nexus_atende.work_items WHERE tenant_id = :tenant_id AND id = :id
                    AND status = 'processing' AND attempts = :attempts FOR UPDATE
            """), {"tenant_id": tenant_id, "id": work.id, "attempts": work.attempts})
            active = reservation.one_or_none()
            if active is None:
                return
            status: WorkStatus = "cancelled"
            retry_after = 30
            if row and (row["sender_type"] == "bot" and row["state"] == ("waiting" if active.allow_waiting else "bot")
                        or row["sender_type"] == "operator" and row["state"] == "assigned"
                        and row["assigned_user_id"] == row["sender_id"]):
                session_id = active.openwa_session_id
                status = "failed"
                if session_id and session_id == row["openwa_session_id"] and not row["openwa_number_verified"]:
                    status = "pending"
                elif session_id and session_id == row["openwa_session_id"]:
                    dispatch = await send(session_id, row["chat_id"], row["content"])
                    status = dispatch.status
                    if dispatch.retry_after is not None:
                        retry_after = dispatch.retry_after
                    if dispatch.provider_id:
                        await connection.execute(text("""
                            UPDATE nexus_atende.messages SET openwa_session_id = :session_id, openwa_message_id = :provider_id
                            WHERE tenant_id = :tenant_id AND id = :message_id
                        """), {"tenant_id": tenant_id, "message_id": work.message_id,
                                "session_id": session_id, "provider_id": dispatch.provider_id})
                        await connection.execute(text("""
                            UPDATE nexus_atende.conversations SET last_interaction = greatest(last_interaction, now())
                            WHERE tenant_id = :tenant_id AND id = :conversation_id
                        """), {"tenant_id": tenant_id, "conversation_id": work.conversation_id})
            await finish(connection, tenant_id, work.id, status, retry_after=retry_after)
