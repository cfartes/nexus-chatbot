"""Persist product origins and the opening of each attendance."""

from alembic import op

revision = "0012_conversation_opening"
down_revision = "0011_whatsapp_pairing"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE nexus_atende.contact_origins (
            tenant_id uuid NOT NULL REFERENCES nexus_atende.tenants(id),
            slug text NOT NULL CHECK (slug ~ '^[a-z0-9]+(-[a-z0-9]+)*$' AND length(slug) <= 50),
            name text NOT NULL CHECK (length(name) BETWEEN 1 AND 100),
            PRIMARY KEY (tenant_id, slug)
        )
    """)
    op.execute("ALTER TABLE nexus_atende.contact_origins ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE nexus_atende.contact_origins FORCE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY tenant_scope ON nexus_atende.contact_origins TO nexus_atende_app
        USING (tenant_id = nullif(current_setting('nexus.tenant_id', true), '')::uuid)
    """)
    op.execute("GRANT SELECT, INSERT, UPDATE ON nexus_atende.contact_origins TO nexus_atende_app")
    op.execute("""
        ALTER TABLE nexus_atende.conversations
        DROP CONSTRAINT conversations_state_check,
        ADD CHECK (state IN ('bot', 'waiting', 'assigned', 'closed')),
        ADD COLUMN opening_pending boolean NOT NULL DEFAULT false,
        ADD COLUMN opening_question text,
        ADD COLUMN origin_slug text,
        ADD FOREIGN KEY (tenant_id, origin_slug) REFERENCES nexus_atende.contact_origins(tenant_id, slug)
    """)


def downgrade() -> None:
    raise RuntimeError("Conversation opening data cannot be removed by automatic rollback.")
