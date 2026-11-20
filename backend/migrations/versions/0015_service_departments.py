"""Add service departments and client registration details."""

from alembic import op

revision = "0015_service_departments"
down_revision = "0014_transfer_notices"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE nexus_atende.users
            ADD COLUMN department text NOT NULL DEFAULT 'sac' CHECK (department IN ('comercial', 'financeiro', 'suporte', 'sac')),
            ADD COLUMN deleted_at timestamptz,
            DROP CONSTRAINT users_email_key
    """)
    op.execute("CREATE UNIQUE INDEX users_email_available_idx ON nexus_atende.users(email) WHERE deleted_at IS NULL")
    op.execute("GRANT UPDATE (department, deleted_at, email) ON nexus_atende.users TO nexus_atende_app")
    op.execute("""
        ALTER TABLE nexus_atende.conversations ADD COLUMN department text
            CHECK (department IN ('comercial', 'financeiro', 'suporte', 'sac')),
            ADD COLUMN awaiting_department boolean NOT NULL DEFAULT false
    """)
    op.execute("ALTER TABLE nexus_atende.tenants ADD COLUMN client_details jsonb NOT NULL DEFAULT '{}'::jsonb")
    op.execute("GRANT UPDATE (client_details) ON nexus_atende.tenants TO nexus_atende_app")
    op.execute("""
        DROP FUNCTION nexus_atende.client_registry();
        CREATE FUNCTION nexus_atende.client_registry()
        RETURNS TABLE (id uuid, name text, archived_at timestamptz, admin_invite_pending boolean, details jsonb)
        LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog AS $$
            SELECT tenants.id, tenants.name, tenants.archived_at, EXISTS (
                SELECT 1 FROM nexus_atende.users WHERE users.tenant_id = tenants.id
                    AND role = 'admin' AND password_hash = '' AND NOT platform_admin
            ), tenants.client_details FROM nexus_atende.tenants AS tenants ORDER BY tenants.name, tenants.id
        $$;
        REVOKE ALL ON FUNCTION nexus_atende.client_registry() FROM PUBLIC;
        GRANT EXECUTE ON FUNCTION nexus_atende.client_registry() TO nexus_atende_app;
    """)


def downgrade() -> None:
    raise RuntimeError("Client registration and departments cannot be removed by automatic rollback.")
