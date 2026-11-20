"""Track verification of a paired WhatsApp number."""

from alembic import op

revision = "0011_whatsapp_pairing"
down_revision = "0010_whatsapp_phone"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE nexus_atende.tenants ADD COLUMN openwa_number_verified boolean NOT NULL DEFAULT false")
    op.execute("GRANT UPDATE (openwa_session_id, openwa_number_verified) ON nexus_atende.tenants TO nexus_atende_app")


def downgrade() -> None:
    raise RuntimeError("WhatsApp pairing state cannot be removed by automatic rollback.")
