"""Store the assistant name per company."""

from alembic import op

revision = "0018_assistant_name"
down_revision = "0017_inactivity_notice"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE nexus_atende.tenants ADD COLUMN assistant_name text NOT NULL DEFAULT ''
            CHECK (char_length(assistant_name) <= 80);
        GRANT UPDATE (assistant_name) ON nexus_atende.tenants TO nexus_atende_app;
    """)


def downgrade() -> None:
    op.execute("ALTER TABLE nexus_atende.tenants DROP COLUMN assistant_name")
