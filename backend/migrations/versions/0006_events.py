"""Publish tenant-scoped dashboard invalidations after commit."""

from alembic import op

revision = "0006_events"
down_revision = "0005_memory"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE FUNCTION nexus_atende.notify_conversation_change() RETURNS trigger
        LANGUAGE plpgsql SET search_path = pg_catalog AS $$
        BEGIN
            PERFORM pg_notify('nexus_atende_' || replace(NEW.tenant_id::text, '-', ''), '');
            RETURN NEW;
        END;
        $$
    """)
    for table in ("conversations", "messages", "work_items"):
        op.execute(f"""
            CREATE TRIGGER notify_conversation_change AFTER INSERT OR UPDATE ON nexus_atende.{table}
            FOR EACH ROW EXECUTE FUNCTION nexus_atende.notify_conversation_change()
        """)


def downgrade() -> None:
    for table in ("conversations", "messages", "work_items"):
        op.execute(f"DROP TRIGGER notify_conversation_change ON nexus_atende.{table}")
    op.execute("DROP FUNCTION nexus_atende.notify_conversation_change()")
