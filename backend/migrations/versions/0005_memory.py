"""Persist the customer profile and the recap of previous sessions."""

from alembic import op

revision = "0005_memory"
down_revision = "0004_operators"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE nexus_atende.customers
            ADD COLUMN first_seen_at timestamptz NOT NULL DEFAULT now(),
            ADD COLUMN last_seen_at timestamptz NOT NULL DEFAULT now(),
            ADD COLUMN total_interactions bigint NOT NULL DEFAULT 0,
            ADD COLUMN previous_summary text
    """)
    op.execute("""
        UPDATE nexus_atende.customers AS customers SET first_seen_at = stats.first_seen,
            last_seen_at = stats.last_seen, total_interactions = stats.interactions
        FROM (
            SELECT conversations.tenant_id, conversations.customer_id, min(messages.created_at) AS first_seen,
                max(messages.created_at) AS last_seen, count(*) AS interactions
            FROM nexus_atende.conversations AS conversations JOIN nexus_atende.messages AS messages
                ON (conversations.tenant_id, conversations.id) = (messages.tenant_id, messages.conversation_id)
            WHERE messages.sender_type = 'customer' GROUP BY conversations.tenant_id, conversations.customer_id
        ) AS stats WHERE (customers.tenant_id, customers.id) = (stats.tenant_id, stats.customer_id)
    """)


def downgrade() -> None:
    raise RuntimeError("Customer profile data cannot be removed by automatic rollback.")
