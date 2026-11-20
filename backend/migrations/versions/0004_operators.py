"""Support tenant-admin management of human operators."""

from alembic import op

revision = "0004_operators"
down_revision = "0003_work"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE nexus_atende.users ADD COLUMN is_active boolean NOT NULL DEFAULT true")
    op.execute("GRANT INSERT ON nexus_atende.users TO nexus_atende_app")
    op.execute("GRANT UPDATE (name, password_hash, is_active) ON nexus_atende.users TO nexus_atende_app")
    op.execute("CREATE INDEX work_processing_idx ON nexus_atende.work_items (tenant_id, started_at) WHERE status = 'processing'")
    op.execute("""
        CREATE INDEX work_conversation_order_idx ON nexus_atende.work_items
            (tenant_id, conversation_id, kind, created_at, id) WHERE status IN ('pending', 'processing')
    """)


def downgrade() -> None:
    raise RuntimeError("Operator state cannot be removed by an automatic rollback.")
