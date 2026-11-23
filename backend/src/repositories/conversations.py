from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from src.repositories.database import tenant_transaction
from src.repositories.work import enqueue
from src.schemas.auth import Operator
from src.schemas.conversations import ConversationSummary, HistoryMessage, Queue, QueueCounts, TransferNotice

WAITING_SCOPE = """(:admin OR conversations.department IS NULL OR EXISTS (
    SELECT 1 FROM nexus_atende.users WHERE tenant_id = :tenant_id AND id = :actor_id
        AND department = conversations.department
))"""

INACTIVITY_NOTICE = (
    "Estamos aguardando seu retorno. Se precisar de mais ajuda, responda a esta mensagem. "
    "Sem resposta, encerraremos o atendimento em 5 minutos."
)


async def _close_locked(connection: AsyncConnection, tenant_id: UUID, conversation_id: UUID) -> bool:
    values = {"tenant_id": tenant_id, "id": conversation_id}
    sending = await connection.scalar(text("""
        SELECT 1 FROM nexus_atende.work_items
        WHERE tenant_id = :tenant_id AND conversation_id = :id AND kind = 'whatsapp'
            AND NOT inactivity_notice AND NOT support_status_reply AND status IN ('pending', 'processing') LIMIT 1
    """), values)
    if sending is not None:
        return False
    await connection.execute(text("""
        UPDATE nexus_atende.support_tickets SET closed_at = clock_timestamp()
        WHERE tenant_id = :tenant_id AND conversation_id = :id AND closed_at IS NULL
    """), values)
    await connection.execute(text("""
        UPDATE nexus_atende.conversations
        SET state = 'closed', assigned_user_id = NULL, opening_pending = true,
            opening_question = NULL, origin_slug = NULL, department = NULL, awaiting_department = false,
            inactivity_due_at = NULL, inactivity_notice_id = NULL
        WHERE tenant_id = :tenant_id AND id = :id
    """), values)
    await connection.execute(text("""
        UPDATE nexus_atende.work_items SET status = 'cancelled'
        WHERE tenant_id = :tenant_id AND conversation_id = :id AND status IN ('pending', 'processing')
            AND (kind = 'rag' OR inactivity_notice OR (kind = 'notify' AND status = 'pending'))
    """), values)
    return True


class ConversationRepository:
    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def operators(self, tenant_id: UUID) -> list[Operator]:
        async with tenant_transaction(self._engine, tenant_id) as connection:
            result = await connection.execute(text("""
                SELECT tenant_id, id, name, role FROM nexus_atende.users
                WHERE tenant_id = :tenant_id AND is_active ORDER BY name, id
            """), {"tenant_id": tenant_id})
            return [Operator.model_validate(row) for row in result.mappings()]

    async def list_queue(self, actor: Operator, queue: Queue, limit: int, offset: int, focus: UUID | None = None) -> list[ConversationSummary]:
        state = "assigned" if queue == "mine" else queue
        async with tenant_transaction(self._engine, actor.tenant_id) as connection:
            result = await connection.execute(text(f"""
                SELECT conversations.id, customers.chat_id, customers.name AS customer_name,
                    conversations.state, conversations.assigned_user_id, conversations.last_interaction,
                    origins.name AS origin_name, conversations.department, ticket.support_ticket
                FROM nexus_atende.conversations AS conversations
                JOIN nexus_atende.customers AS customers
                    ON (customers.tenant_id, customers.id) = (conversations.tenant_id, conversations.customer_id)
                LEFT JOIN nexus_atende.contact_origins AS origins
                    ON (origins.tenant_id, origins.slug) = (conversations.tenant_id, conversations.origin_slug)
                LEFT JOIN LATERAL (
                    SELECT jsonb_build_object('id', id, 'product', product, 'details', details, 'closed_at', closed_at)
                        AS support_ticket
                    FROM nexus_atende.support_tickets
                    WHERE tenant_id = conversations.tenant_id AND conversation_id = conversations.id
                    ORDER BY opened_at DESC, id DESC LIMIT 1
                ) AS ticket ON true
                WHERE conversations.tenant_id = :tenant_id AND conversations.state = :state
                    AND (NOT :mine OR conversations.assigned_user_id = :actor_id)
                    AND (conversations.state <> 'waiting' OR {WAITING_SCOPE})
                ORDER BY (conversations.id = :focus) DESC NULLS LAST, conversations.last_interaction DESC, conversations.id DESC
                LIMIT :limit OFFSET :offset
            """), {
                "tenant_id": actor.tenant_id, "state": state, "mine": queue == "mine",
                "actor_id": actor.id, "limit": limit, "offset": offset, "focus": focus, "admin": actor.role == "admin",
            })
            return [ConversationSummary.model_validate(row) for row in result.mappings()]

    async def queue_counts(self, actor: Operator) -> QueueCounts:
        async with tenant_transaction(self._engine, actor.tenant_id) as connection:
            result = await connection.execute(text(f"""
                SELECT count(*) FILTER (WHERE state = 'waiting' AND {WAITING_SCOPE}) AS waiting,
                    count(*) FILTER (WHERE state = 'bot') AS bot,
                    count(*) FILTER (WHERE state = 'assigned' AND assigned_user_id = :actor_id) AS mine,
                    CASE WHEN :admin THEN count(*) FILTER (WHERE state = 'assigned') END AS assigned,
                    CASE WHEN :admin THEN count(*) FILTER (WHERE state = 'closed') END AS closed
                FROM nexus_atende.conversations WHERE tenant_id = :tenant_id
            """), {"tenant_id": actor.tenant_id, "actor_id": actor.id, "admin": actor.role == "admin"})
            return QueueCounts.model_validate(result.mappings().one())

    async def history(
        self, actor: Operator, conversation_id: UUID, limit: int, before: UUID | None,
    ) -> list[HistoryMessage] | None:
        async with tenant_transaction(self._engine, actor.tenant_id) as connection:
            visible = await connection.scalar(text("""
                SELECT id FROM nexus_atende.conversations
                WHERE tenant_id = :tenant_id AND id = :conversation_id
                    AND (:admin OR state <> 'assigned' OR assigned_user_id = :actor_id)
                    AND (:admin OR state <> 'waiting' OR department IS NULL OR EXISTS (
                        SELECT 1 FROM nexus_atende.users WHERE tenant_id = :tenant_id AND id = :actor_id
                            AND users.department = conversations.department
                    ))
                FOR SHARE
            """), {
                "tenant_id": actor.tenant_id, "conversation_id": conversation_id,
                "admin": actor.role == "admin", "actor_id": actor.id,
            })
            if visible is None:
                return None
            result = await connection.execute(text("""
                SELECT messages.id, messages.sender_type, messages.sender_id, messages.content,
                    messages.created_at, work.status AS delivery_status
                FROM nexus_atende.messages AS messages
                LEFT JOIN nexus_atende.work_items AS work ON work.tenant_id = messages.tenant_id
                    AND work.message_id = messages.id AND work.kind = 'whatsapp'
                WHERE messages.tenant_id = :tenant_id AND messages.conversation_id = :conversation_id
                    AND (CAST(:before AS uuid) IS NULL OR (messages.created_at, messages.id) < (
                        SELECT created_at, id FROM nexus_atende.messages
                        WHERE tenant_id = :tenant_id AND conversation_id = :conversation_id AND id = :before
                    ))
                ORDER BY messages.created_at DESC, messages.id DESC LIMIT :limit
            """), {
                "tenant_id": actor.tenant_id, "conversation_id": conversation_id, "before": before, "limit": limit,
            })
            return [HistoryMessage.model_validate(row) for row in result.mappings()]

    async def claim(self, actor: Operator, conversation_id: UUID) -> bool:
        async with tenant_transaction(self._engine, actor.tenant_id) as connection:
            department = await connection.scalar(text("""
                SELECT department FROM nexus_atende.users WHERE tenant_id = :tenant_id AND id = :id AND is_active FOR SHARE
            """), {"tenant_id": actor.tenant_id, "id": actor.id})
            if department is None:
                return False
            claimed = await connection.scalar(text("""
                UPDATE nexus_atende.conversations SET state = 'assigned', assigned_user_id = :actor_id
                WHERE tenant_id = :tenant_id AND id = :conversation_id AND state = 'waiting'
                    AND (:admin OR department IS NULL OR department = :department)
                RETURNING id
            """), {"tenant_id": actor.tenant_id, "conversation_id": conversation_id, "actor_id": actor.id,
                    "admin": actor.role == "admin", "department": department})
            return claimed is not None

    async def close(self, actor: Operator, conversation_id: UUID) -> bool:
        values = {"tenant_id": actor.tenant_id, "id": conversation_id, "actor_id": actor.id, "admin": actor.role == "admin"}
        async with tenant_transaction(self._engine, actor.tenant_id) as connection:
            current = await connection.scalar(text("""
                SELECT id FROM nexus_atende.conversations
                WHERE tenant_id = :tenant_id AND id = :id AND state <> 'closed'
                    AND (:admin OR assigned_user_id = :actor_id)
                FOR UPDATE
            """), values)
            if current is None:
                return False
            return await _close_locked(connection, actor.tenant_id, conversation_id)

    async def process_inactivity(self, tenant_id: UUID, *, can_notify: bool) -> None:
        async with tenant_transaction(self._engine, tenant_id) as connection:
            due = await connection.execute(text("""
                SELECT conversation.id, conversation.inactivity_notice_id
                FROM nexus_atende.conversations AS conversation
                JOIN nexus_atende.tenants AS tenant ON tenant.id = conversation.tenant_id
                WHERE conversation.tenant_id = :tenant_id AND tenant.archived_at IS NULL
                    AND conversation.state IN ('bot', 'assigned')
                    AND conversation.inactivity_due_at <= now()
                    AND (conversation.inactivity_notice_id IS NOT NULL
                         OR (:can_notify AND tenant.openwa_session_id IS NOT NULL AND tenant.openwa_number_verified))
                    AND NOT EXISTS (
                        SELECT 1 FROM nexus_atende.work_items AS work
                        WHERE work.tenant_id = :tenant_id AND work.conversation_id = conversation.id
                            AND work.kind IN ('whatsapp', 'rag') AND work.status IN ('pending', 'processing')
                    )
                ORDER BY conversation.inactivity_due_at, conversation.id LIMIT 20
                FOR UPDATE OF conversation SKIP LOCKED
            """), {"tenant_id": tenant_id, "can_notify": can_notify})
            for row in due:
                if row.inactivity_notice_id is not None:
                    await _close_locked(connection, tenant_id, row.id)
                    continue
                values = {"tenant_id": tenant_id, "id": row.id}
                message_id = await connection.scalar(text("""
                    INSERT INTO nexus_atende.messages (tenant_id, conversation_id, sender_type, content)
                    VALUES (:tenant_id, :id, 'bot', :content) RETURNING id
                """), {**values, "content": INACTIVITY_NOTICE})
                await connection.execute(text("""
                    UPDATE nexus_atende.conversations SET inactivity_due_at = NULL, inactivity_notice_id = :message_id
                    WHERE tenant_id = :tenant_id AND id = :id
                """), {**values, "message_id": message_id})
                await enqueue(connection, tenant_id, row.id, "whatsapp", message_id, inactivity_notice=True)

    async def transfer(self, actor: Operator, conversation_id: UUID, user_id: UUID) -> bool:
        async with tenant_transaction(self._engine, actor.tenant_id) as connection:
            values = {"tenant_id": actor.tenant_id, "id": conversation_id, "user_id": user_id,
                      "actor_id": actor.id, "admin": actor.role == "admin"}
            active = await connection.scalar(text("""
                SELECT id FROM nexus_atende.users WHERE tenant_id = :tenant_id AND id = :user_id AND is_active FOR SHARE
            """), values)
            if active is None:
                return False
            current = await connection.scalar(text("""
                SELECT assigned_user_id FROM nexus_atende.conversations
                WHERE tenant_id = :tenant_id AND id = :id AND state = 'assigned'
                    AND (:admin OR assigned_user_id = :actor_id) FOR UPDATE
            """), values)
            if current is None:
                return False
            if current == user_id:
                return True
            await connection.execute(text("""
                UPDATE nexus_atende.conversations SET assigned_user_id = :user_id, last_interaction = clock_timestamp()
                WHERE tenant_id = :tenant_id AND id = :id
            """), values)
            await connection.execute(text("""
                UPDATE nexus_atende.work_items SET acknowledged_at = now(),
                    status = CASE WHEN status = 'pending' THEN 'cancelled' ELSE status END
                WHERE tenant_id = :tenant_id AND conversation_id = :id AND recipient_user_id IS NOT NULL
                    AND (acknowledged_at IS NULL OR status = 'pending')
            """), values)
            await connection.execute(text("""
                INSERT INTO nexus_atende.work_items (tenant_id, conversation_id, kind, recipient_user_id)
                VALUES (:tenant_id, :id, 'notify', :user_id)
            """), values)
            return True

    async def transfer_notices(self, actor: Operator) -> list[TransferNotice]:
        async with tenant_transaction(self._engine, actor.tenant_id) as connection:
            result = await connection.execute(text("""
                SELECT work.id, work.conversation_id FROM nexus_atende.work_items AS work
                JOIN nexus_atende.conversations AS conversation
                    ON (conversation.tenant_id, conversation.id) = (work.tenant_id, work.conversation_id)
                WHERE work.tenant_id = :tenant_id AND work.recipient_user_id = :actor
                    AND work.acknowledged_at IS NULL AND conversation.assigned_user_id = :actor
                ORDER BY work.created_at DESC, work.id DESC
            """), {"tenant_id": actor.tenant_id, "actor": actor.id})
            return [TransferNotice.model_validate(row) for row in result.mappings()]

    async def acknowledge_transfer(self, actor: Operator, notice_id: UUID) -> None:
        async with tenant_transaction(self._engine, actor.tenant_id) as connection:
            await connection.execute(text("""
                UPDATE nexus_atende.work_items SET acknowledged_at = now()
                WHERE tenant_id = :tenant_id AND id = :id AND recipient_user_id = :actor AND acknowledged_at IS NULL
            """), {"tenant_id": actor.tenant_id, "id": notice_id, "actor": actor.id})
