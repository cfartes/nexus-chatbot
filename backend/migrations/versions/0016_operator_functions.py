"""Register tenant-specific operator functions."""

from alembic import op

revision = "0016_operator_functions"
down_revision = "0015_service_departments"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE nexus_atende.operator_functions (
            tenant_id uuid NOT NULL REFERENCES nexus_atende.tenants(id),
            id uuid NOT NULL DEFAULT gen_random_uuid(),
            name text NOT NULL,
            department text NOT NULL CHECK (department IN ('comercial', 'financeiro', 'suporte', 'sac')),
            PRIMARY KEY (tenant_id, id),
            UNIQUE (tenant_id, id, department)
        );
        CREATE UNIQUE INDEX operator_functions_name_idx ON nexus_atende.operator_functions (tenant_id, lower(name));
        ALTER TABLE nexus_atende.users ADD COLUMN function_id uuid,
            ADD FOREIGN KEY (tenant_id, function_id, department)
            REFERENCES nexus_atende.operator_functions (tenant_id, id, department) ON UPDATE CASCADE;
        CREATE INDEX users_operator_function_idx ON nexus_atende.users (tenant_id, function_id) WHERE function_id IS NOT NULL;
        INSERT INTO nexus_atende.operator_functions (tenant_id, name, department)
        SELECT tenants.id, defaults.name, defaults.department FROM nexus_atende.tenants CROSS JOIN
            (VALUES ('Comercial','comercial'), ('Financeiro','financeiro'), ('Suporte','suporte'), ('SAC','sac')) AS defaults(name, department);
        UPDATE nexus_atende.users AS users SET function_id = functions.id
        FROM nexus_atende.operator_functions AS functions
        WHERE users.tenant_id = functions.tenant_id AND users.department = functions.department
            AND users.role = 'operator' AND users.deleted_at IS NULL;
        ALTER TABLE nexus_atende.operator_functions ENABLE ROW LEVEL SECURITY;
        ALTER TABLE nexus_atende.operator_functions FORCE ROW LEVEL SECURITY;
        CREATE POLICY tenant_scope ON nexus_atende.operator_functions
            USING (tenant_id = nullif(current_setting('nexus.tenant_id', true), '')::uuid);
        GRANT SELECT, INSERT, UPDATE, DELETE ON nexus_atende.operator_functions TO nexus_atende_app;
        GRANT UPDATE (function_id) ON nexus_atende.users TO nexus_atende_app;
    """)


def downgrade() -> None:
    raise RuntimeError("Registered operator functions cannot be removed by automatic rollback.")
