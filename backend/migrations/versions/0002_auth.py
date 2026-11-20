"""Persist operator sessions and login limits."""

from alembic import op

revision = "0002_auth"
down_revision = "0001_atendimento"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE UNIQUE INDEX users_email_normalized_idx ON nexus_atende.users (lower(email))")
    op.execute("""
        CREATE TABLE nexus_atende.sessions (
            tenant_id uuid NOT NULL,
            token_hash text NOT NULL,
            user_id uuid NOT NULL,
            expires_at timestamptz NOT NULL DEFAULT now() + interval '8 hours',
            PRIMARY KEY (tenant_id, token_hash),
            FOREIGN KEY (tenant_id, user_id) REFERENCES nexus_atende.users (tenant_id, id)
                ON DELETE CASCADE
        )
    """)
    op.execute("ALTER TABLE nexus_atende.sessions ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE nexus_atende.sessions FORCE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY tenant_scope ON nexus_atende.sessions TO nexus_atende_app
        USING (tenant_id = nullif(current_setting('nexus.tenant_id', true), '')::uuid)
    """)
    op.execute("GRANT SELECT, INSERT, DELETE ON nexus_atende.sessions TO nexus_atende_app")
    op.execute("""
        CREATE TABLE nexus_atende.login_limits (
            key_hash text PRIMARY KEY,
            attempts integer NOT NULL,
            expires_at timestamptz NOT NULL
        )
    """)
    op.execute("ALTER TABLE nexus_atende.login_limits ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE nexus_atende.login_limits FORCE ROW LEVEL SECURITY")
    op.execute("CREATE POLICY runtime_limits ON nexus_atende.login_limits TO nexus_atende_app USING (true)")
    op.execute("GRANT SELECT, INSERT, UPDATE ON nexus_atende.login_limits TO nexus_atende_app")


def downgrade() -> None:
    raise RuntimeError("Authentication data cannot be removed by an automatic rollback.")
