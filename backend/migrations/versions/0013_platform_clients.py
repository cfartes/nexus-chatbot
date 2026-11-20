"""Separate platform administration and archive client accounts."""

from alembic import op

revision = "0013_platform_clients"
down_revision = "0012_conversation_opening"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE nexus_atende.users ADD COLUMN platform_admin boolean NOT NULL DEFAULT false CHECK (NOT platform_admin OR role = 'admin')")
    op.execute("ALTER TABLE nexus_atende.tenants ADD COLUMN archived_at timestamptz")
    op.execute("GRANT INSERT, UPDATE (name, archived_at) ON nexus_atende.tenants TO nexus_atende_app")
    op.execute("""
        CREATE FUNCTION nexus_atende.client_registry()
        RETURNS TABLE (id uuid, name text, archived_at timestamptz, admin_invite_pending boolean)
        LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog AS $$
            SELECT tenants.id, tenants.name, tenants.archived_at, EXISTS (
                SELECT 1 FROM nexus_atende.users WHERE users.tenant_id = tenants.id
                    AND role = 'admin' AND password_hash = '' AND NOT platform_admin
            ) FROM nexus_atende.tenants AS tenants ORDER BY tenants.name, tenants.id
        $$;
        REVOKE ALL ON FUNCTION nexus_atende.client_registry() FROM PUBLIC;
        GRANT EXECUTE ON FUNCTION nexus_atende.client_registry() TO nexus_atende_app;
    """)


def downgrade() -> None:
    raise RuntimeError("Platform client data cannot be removed by automatic rollback.")
