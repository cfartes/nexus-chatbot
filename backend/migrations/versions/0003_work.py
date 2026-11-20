"""Add the durable work queue and tenant knowledge base."""

from alembic import op

revision = "0003_work"
down_revision = "0002_auth"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE nexus_atende.work_items (
            tenant_id uuid NOT NULL,
            id uuid NOT NULL DEFAULT gen_random_uuid(),
            conversation_id uuid NOT NULL,
            message_id uuid,
            openwa_session_id uuid,
            kind text NOT NULL CHECK (kind IN ('whatsapp', 'notify', 'rag')),
            status text NOT NULL DEFAULT 'pending'
                CHECK (status IN ('pending', 'processing', 'sent', 'failed', 'uncertain', 'cancelled')),
            attempts integer NOT NULL DEFAULT 0,
            allow_waiting boolean NOT NULL DEFAULT false,
            available_at timestamptz NOT NULL DEFAULT now(),
            started_at timestamptz,
            created_at timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (tenant_id, id),
            FOREIGN KEY (tenant_id, conversation_id) REFERENCES nexus_atende.conversations (tenant_id, id),
            FOREIGN KEY (tenant_id, message_id) REFERENCES nexus_atende.messages (tenant_id, id),
            CHECK ((message_id IS NULL) = (kind = 'notify')),
            UNIQUE (tenant_id, kind, message_id)
        )
    """)
    op.execute("""
        CREATE INDEX work_pending_idx ON nexus_atende.work_items (tenant_id, available_at, created_at)
        WHERE status = 'pending'
    """)
    op.execute("""
        CREATE TABLE nexus_atende.knowledge_chunks (
            tenant_id uuid NOT NULL REFERENCES nexus_atende.tenants (id),
            source text NOT NULL,
            position integer NOT NULL,
            content text NOT NULL,
            embedding vector(768) NOT NULL,
            PRIMARY KEY (tenant_id, source, position)
        )
    """)
    for table in ("work_items", "knowledge_chunks"):
        op.execute(f"ALTER TABLE nexus_atende.{table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE nexus_atende.{table} FORCE ROW LEVEL SECURITY")
        op.execute(f"""
            CREATE POLICY tenant_scope ON nexus_atende.{table} TO nexus_atende_app
            USING (tenant_id = nullif(current_setting('nexus.tenant_id', true), '')::uuid)
        """)
    op.execute("GRANT SELECT, INSERT, UPDATE ON nexus_atende.work_items TO nexus_atende_app")
    op.execute("GRANT SELECT, INSERT, DELETE ON nexus_atende.knowledge_chunks TO nexus_atende_app")


def downgrade() -> None:
    raise RuntimeError("Persisted work and knowledge cannot be removed by automatic rollback.")
