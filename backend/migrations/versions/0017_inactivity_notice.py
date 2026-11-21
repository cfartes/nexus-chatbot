"""Store WhatsApp inactivity deadlines and queued warnings."""

from alembic import op

revision = "0017_inactivity_notice"
down_revision = "0016_operator_functions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE nexus_atende.conversations ADD COLUMN inactivity_due_at timestamptz,
            ADD COLUMN inactivity_notice_id uuid;
        ALTER TABLE nexus_atende.work_items ADD COLUMN inactivity_notice boolean NOT NULL DEFAULT false;
        CREATE INDEX conversations_inactivity_idx ON nexus_atende.conversations (tenant_id, inactivity_due_at)
        WHERE inactivity_due_at IS NOT NULL AND state IN ('bot', 'assigned');
    """)


def downgrade() -> None:
    raise RuntimeError("Inactivity state cannot be removed by automatic rollback.")
