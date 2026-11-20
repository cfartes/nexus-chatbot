"""Allow the worker to prune expired authentication records."""

from alembic import op

revision = "0007_auth_retention"
down_revision = "0006_events"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE INDEX sessions_expiry_idx ON nexus_atende.sessions (tenant_id, expires_at)")
    op.execute("CREATE INDEX login_limits_expiry_idx ON nexus_atende.login_limits (expires_at)")
    op.execute("GRANT DELETE ON nexus_atende.login_limits TO nexus_atende_app")


def downgrade() -> None:
    op.execute("REVOKE DELETE ON nexus_atende.login_limits FROM nexus_atende_app")
    op.execute("DROP INDEX nexus_atende.login_limits_expiry_idx")
    op.execute("DROP INDEX nexus_atende.sessions_expiry_idx")
