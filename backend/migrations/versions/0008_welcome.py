"""Allow each company to set a standard welcome message."""

from alembic import op

revision = "0008_welcome"
down_revision = "0007_auth_retention"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE nexus_atende.tenants ADD COLUMN welcome_message text NOT NULL DEFAULT ''")
    op.execute("ALTER TABLE nexus_atende.tenants ADD CHECK (char_length(welcome_message) <= 500)")
    op.execute("GRANT UPDATE (welcome_message) ON nexus_atende.tenants TO nexus_atende_app")


def downgrade() -> None:
    raise RuntimeError("The saved welcome message cannot be removed by automatic rollback.")
