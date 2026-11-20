"""Allow authenticated tenant settings to update the WhatsApp number."""

from alembic import op

revision = "0010_whatsapp_phone"
down_revision = "0009_integrations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("GRANT UPDATE (phone_number) ON nexus_atende.tenants TO nexus_atende_app")


def downgrade() -> None:
    op.execute("REVOKE UPDATE (phone_number) ON nexus_atende.tenants FROM nexus_atende_app")
