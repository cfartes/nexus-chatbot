"""Store tenant integrations and operator invitation hashes."""

from alembic import op

revision = "0009_integrations"
down_revision = "0008_welcome"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE nexus_atende.integrations (
            tenant_id uuid PRIMARY KEY REFERENCES nexus_atende.tenants (id),
            config jsonb NOT NULL DEFAULT '{}'::jsonb
        )
    """)
    op.execute("ALTER TABLE nexus_atende.integrations ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE nexus_atende.integrations FORCE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY tenant_scope ON nexus_atende.integrations TO nexus_atende_app
        USING (tenant_id = nullif(current_setting('nexus.tenant_id', true), '')::uuid)
    """)
    op.execute("GRANT SELECT, INSERT, UPDATE ON nexus_atende.integrations TO nexus_atende_app")
    op.execute("""
        ALTER TABLE nexus_atende.users ADD COLUMN invite_hash text, ADD COLUMN invite_expires timestamptz
    """)
    op.execute("GRANT UPDATE (invite_hash, invite_expires) ON nexus_atende.users TO nexus_atende_app")
    op.execute("""
        CREATE UNIQUE INDEX users_invite_idx ON nexus_atende.users (tenant_id, invite_hash)
        WHERE invite_hash IS NOT NULL
    """)
    op.execute("ALTER TABLE nexus_atende.knowledge_chunks ADD COLUMN embedding_space text NOT NULL DEFAULT 'openai:text-embedding-3-small'")


def downgrade() -> None:
    raise RuntimeError("Integration settings and invitations cannot be removed by automatic rollback.")
