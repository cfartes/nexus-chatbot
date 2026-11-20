"""Create the tenant-scoped customer service schema."""

from alembic import op

revision = "0001_atendimento"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute("CREATE ROLE nexus_atende_app NOLOGIN NOSUPERUSER NOBYPASSRLS")
    op.execute("CREATE SCHEMA nexus_atende")
    op.execute("GRANT USAGE ON SCHEMA nexus_atende TO nexus_atende_app")
    op.execute("""
        CREATE TABLE nexus_atende.tenants (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            name text NOT NULL,
            phone_number text UNIQUE,
            openwa_session_id uuid UNIQUE
        )
    """)
    op.execute("""
        CREATE TABLE nexus_atende.users (
            tenant_id uuid NOT NULL REFERENCES nexus_atende.tenants (id),
            id uuid NOT NULL DEFAULT gen_random_uuid(),
            email text NOT NULL UNIQUE,
            name text NOT NULL,
            password_hash text NOT NULL,
            role text NOT NULL CHECK (role IN ('admin', 'operator')),
            PRIMARY KEY (tenant_id, id)
        )
    """)
    op.execute("""
        CREATE TABLE nexus_atende.customers (
            tenant_id uuid NOT NULL REFERENCES nexus_atende.tenants (id),
            id uuid NOT NULL DEFAULT gen_random_uuid(),
            chat_id text NOT NULL,
            name text,
            PRIMARY KEY (tenant_id, id),
            UNIQUE (tenant_id, chat_id)
        )
    """)
    op.execute("""
        CREATE TABLE nexus_atende.conversations (
            tenant_id uuid NOT NULL,
            id uuid NOT NULL DEFAULT gen_random_uuid(),
            customer_id uuid NOT NULL,
            assigned_user_id uuid,
            state text NOT NULL DEFAULT 'waiting',
            last_interaction timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (tenant_id, id),
            UNIQUE (tenant_id, customer_id),
            FOREIGN KEY (tenant_id, customer_id)
                REFERENCES nexus_atende.customers (tenant_id, id),
            FOREIGN KEY (tenant_id, assigned_user_id)
                REFERENCES nexus_atende.users (tenant_id, id),
            CHECK (state IN ('bot', 'waiting', 'assigned')),
            CHECK ((state = 'assigned') = (assigned_user_id IS NOT NULL))
        )
    """)
    op.execute("""
        CREATE TABLE nexus_atende.messages (
            tenant_id uuid NOT NULL,
            id uuid NOT NULL DEFAULT gen_random_uuid(),
            conversation_id uuid NOT NULL,
            sender_type text NOT NULL CHECK (sender_type IN ('customer', 'bot', 'operator')),
            sender_id uuid,
            openwa_session_id uuid,
            openwa_message_id text,
            content text NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (tenant_id, id),
            FOREIGN KEY (tenant_id, conversation_id)
                REFERENCES nexus_atende.conversations (tenant_id, id),
            FOREIGN KEY (tenant_id, sender_id)
                REFERENCES nexus_atende.users (tenant_id, id),
            CHECK ((sender_type = 'operator') = (sender_id IS NOT NULL)),
            CHECK ((openwa_session_id IS NULL) = (openwa_message_id IS NULL)),
            UNIQUE (tenant_id, openwa_session_id, openwa_message_id)
        )
    """)
    op.execute("""
        CREATE INDEX messages_timeline_idx
        ON nexus_atende.messages (tenant_id, conversation_id, created_at, id)
    """)
    for table in ("tenants", "users", "customers", "conversations", "messages"):
        tenant_column = "id" if table == "tenants" else "tenant_id"
        op.execute(f"ALTER TABLE nexus_atende.{table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE nexus_atende.{table} FORCE ROW LEVEL SECURITY")
        op.execute(f"""
            CREATE POLICY tenant_scope ON nexus_atende.{table} TO nexus_atende_app
            USING ({tenant_column} = nullif(current_setting('nexus.tenant_id', true), '')::uuid)
        """)
        privileges = "SELECT" if table in ("tenants", "users") else "SELECT, INSERT, UPDATE"
        op.execute(f"GRANT {privileges} ON nexus_atende.{table} TO nexus_atende_app")


def downgrade() -> None:
    raise RuntimeError("The initial migration owns persisted data and cannot be downgraded.")
