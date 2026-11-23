"""Track support tickets and permit status replies in any conversation state."""

from alembic import op

revision = "0020_support_tickets"
down_revision = "0019_knowledge_download"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE nexus_atende.support_tickets (
            tenant_id uuid NOT NULL,
            id uuid NOT NULL DEFAULT gen_random_uuid(),
            conversation_id uuid NOT NULL,
            product text,
            details text NOT NULL,
            opened_at timestamptz NOT NULL DEFAULT clock_timestamp(),
            closed_at timestamptz,
            PRIMARY KEY (tenant_id, id),
            FOREIGN KEY (tenant_id, conversation_id) REFERENCES nexus_atende.conversations (tenant_id, id)
        );
        ALTER TABLE nexus_atende.support_tickets ENABLE ROW LEVEL SECURITY;
        ALTER TABLE nexus_atende.support_tickets FORCE ROW LEVEL SECURITY;
        CREATE POLICY tenant_scope ON nexus_atende.support_tickets TO nexus_atende_app
            USING (tenant_id = nullif(current_setting('nexus.tenant_id', true), '')::uuid)
            WITH CHECK (tenant_id = nullif(current_setting('nexus.tenant_id', true), '')::uuid);
        GRANT SELECT, INSERT, UPDATE (closed_at) ON nexus_atende.support_tickets TO nexus_atende_app;
        CREATE UNIQUE INDEX support_tickets_one_open
            ON nexus_atende.support_tickets (tenant_id, conversation_id) WHERE closed_at IS NULL;
        CREATE INDEX support_tickets_recent
            ON nexus_atende.support_tickets (tenant_id, conversation_id, opened_at DESC, id DESC);
        ALTER TABLE nexus_atende.work_items ADD COLUMN support_status_reply boolean NOT NULL DEFAULT false;
    """)


def downgrade() -> None:
    raise RuntimeError("Downgrade would discard support tickets.")
