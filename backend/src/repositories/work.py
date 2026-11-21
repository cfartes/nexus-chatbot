from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from src.repositories.database import tenant_transaction
from src.schemas.work import EmailNotice, WorkItem, WorkKind, WorkStatus


async def enqueue(
    connection: AsyncConnection, tenant_id: UUID, conversation_id: UUID,
    kind: WorkKind, message_id: UUID | None = None, *, allow_waiting: bool = False, inactivity_notice: bool = False,
) -> None:
    await connection.execute(text("""
        INSERT INTO nexus_atende.work_items (tenant_id, conversation_id, kind, message_id, allow_waiting, inactivity_notice, openwa_session_id, created_at)
        VALUES (:tenant_id, :conversation_id, :kind, :message_id, :allow_waiting, :inactivity_notice,
            CASE WHEN :kind = 'whatsapp' THEN (
                SELECT openwa_session_id FROM nexus_atende.tenants WHERE id = :tenant_id
            ) ELSE NULL END, clock_timestamp())
    """), {"tenant_id": tenant_id, "conversation_id": conversation_id, "kind": kind,
            "message_id": message_id, "allow_waiting": allow_waiting, "inactivity_notice": inactivity_notice})


async def finish(
    connection: AsyncConnection, tenant_id: UUID, work_id: UUID, status: WorkStatus, *, retry_after: int = 30,
) -> None:
    await connection.execute(text("""
        UPDATE nexus_atende.work_items SET status = :status,
            available_at = CASE WHEN :status = 'pending'
                THEN clock_timestamp() + make_interval(secs => :retry_after) ELSE available_at END
        WHERE tenant_id = :tenant_id AND id = :id AND status = 'processing'
    """), {"tenant_id": tenant_id, "id": work_id, "status": status, "retry_after": retry_after})


class WorkRepository:
    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def claim(self, tenant_id: UUID, email_enabled: bool, whatsapp_enabled: bool, *, direct_email_enabled: bool = False) -> WorkItem | None:
        async with tenant_transaction(self._engine, tenant_id) as connection:
            enabled = await connection.scalar(text("""
                SELECT 1 FROM nexus_atende.tenants WHERE id = :tenant_id AND archived_at IS NULL FOR SHARE
            """), {"tenant_id": tenant_id})
            if enabled is None:
                return None
            await connection.execute(text("""
                WITH expired AS (
                    SELECT id FROM nexus_atende.work_items
                    WHERE tenant_id = :tenant_id AND status = 'processing'
                        AND started_at < now() - interval '5 minutes'
                    FOR UPDATE SKIP LOCKED
                )
                UPDATE nexus_atende.work_items AS work SET status = CASE
                    WHEN work.kind = 'whatsapp' THEN 'uncertain'
                    WHEN work.kind = 'rag' OR (work.attempts < 3 AND work.created_at > now() - interval '12 hours')
                        THEN 'pending' ELSE 'failed' END
                FROM expired WHERE work.tenant_id = :tenant_id AND work.id = expired.id
            """), {"tenant_id": tenant_id})
            await connection.execute(text("""
                UPDATE nexus_atende.work_items SET status = 'failed'
                WHERE tenant_id = :tenant_id AND kind = 'notify' AND status = 'pending'
                    AND attempts > 0 AND created_at <= now() - interval '12 hours'
            """), {"tenant_id": tenant_id})
            result = await connection.execute(text("""
                WITH next_item AS (
                    SELECT item.id FROM nexus_atende.work_items AS item
                    WHERE item.tenant_id = :tenant_id AND item.status = 'pending' AND item.available_at <= now()
                        AND (item.kind <> 'notify' OR
                            ((item.recipient_user_id IS NULL AND :email_enabled)
                             OR (item.recipient_user_id IS NOT NULL AND :direct_email_enabled)) AND
                            (item.attempts = 0 OR item.created_at > now() - interval '12 hours'))
                        AND (item.kind <> 'whatsapp' OR :whatsapp_enabled)
                        AND (item.kind = 'notify' OR NOT EXISTS (
                            SELECT 1 FROM nexus_atende.work_items AS earlier
                            WHERE earlier.tenant_id = :tenant_id AND earlier.conversation_id = item.conversation_id
                                AND earlier.kind = item.kind AND earlier.status IN ('pending', 'processing')
                                AND (earlier.created_at, earlier.id) < (item.created_at, item.id)
                        ))
                    ORDER BY item.available_at, item.created_at, item.id LIMIT 1 FOR UPDATE SKIP LOCKED
                )
                UPDATE nexus_atende.work_items AS work SET status = 'processing',
                    attempts = attempts + 1, started_at = now()
                FROM next_item WHERE work.tenant_id = :tenant_id AND work.id = next_item.id
                RETURNING work.id, work.conversation_id, work.message_id, work.kind, work.attempts, work.recipient_user_id
            """), {"tenant_id": tenant_id, "email_enabled": email_enabled, "whatsapp_enabled": whatsapp_enabled,
                    "direct_email_enabled": direct_email_enabled})
            row = result.mappings().one_or_none()
            return WorkItem.model_validate(row) if row is not None else None

    async def email_notice(self, tenant_id: UUID, work: WorkItem) -> EmailNotice | None:
        async with tenant_transaction(self._engine, tenant_id) as connection:
            result = await connection.execute(text("""
                SELECT coalesce(nullif(trim(customer.name), ''), 'Nome não informado') AS customer_name,
                    to_char(item.created_at AT TIME ZONE 'America/Sao_Paulo', 'DD/MM/YYYY HH24:MI') AS started_local,
                    recipient.email AS recipient
                FROM nexus_atende.work_items AS item
                JOIN nexus_atende.conversations AS conversation
                    ON (conversation.tenant_id, conversation.id) = (item.tenant_id, item.conversation_id)
                JOIN nexus_atende.customers AS customer
                    ON (customer.tenant_id, customer.id) = (conversation.tenant_id, conversation.customer_id)
                LEFT JOIN nexus_atende.users AS recipient ON recipient.tenant_id = item.tenant_id
                    AND recipient.id = item.recipient_user_id AND recipient.is_active
                    AND recipient.id = conversation.assigned_user_id AND conversation.state = 'assigned'
                WHERE item.tenant_id = :tenant AND item.id = :id
                    AND (item.recipient_user_id IS NULL OR recipient.email IS NOT NULL)
            """), {"tenant": tenant_id, "id": work.id})
            row = result.mappings().one_or_none()
            return EmailNotice.model_validate(row) if row is not None else None

    async def complete(self, tenant_id: UUID, work: WorkItem, status: WorkStatus) -> None:
        async with tenant_transaction(self._engine, tenant_id) as connection:
            current = await connection.scalar(text("""
                SELECT id FROM nexus_atende.work_items WHERE tenant_id = :tenant_id AND id = :id
                    AND status = 'processing' AND attempts = :attempts FOR UPDATE
            """), {"tenant_id": tenant_id, "id": work.id, "attempts": work.attempts})
            if current is not None:
                await finish(connection, tenant_id, work.id, status)
