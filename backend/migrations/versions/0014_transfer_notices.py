"""Record direct notifications and acknowledgement."""

from alembic import op

revision = "0014_transfer_notices"
down_revision = "0013_platform_clients"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE nexus_atende.work_items ADD COLUMN recipient_user_id uuid,
            ADD COLUMN acknowledged_at timestamptz,
            ADD FOREIGN KEY (tenant_id, recipient_user_id) REFERENCES nexus_atende.users(tenant_id, id),
            ADD CHECK (recipient_user_id IS NULL OR kind = 'notify')
    """)
    op.execute("""
        CREATE INDEX transfer_notice_recipient_idx ON nexus_atende.work_items (tenant_id, recipient_user_id)
        WHERE recipient_user_id IS NOT NULL AND acknowledged_at IS NULL
    """)


def downgrade() -> None:
    raise RuntimeError("Transfer notices cannot be removed by automatic rollback.")
