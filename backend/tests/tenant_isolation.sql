BEGIN;

INSERT INTO nexus_atende.tenants (id, name) VALUES
    ('00000000-0000-0000-0000-000000000001', 'Nexus'),
    ('00000000-0000-0000-0000-000000000002', 'Outra empresa');
INSERT INTO nexus_atende.users (tenant_id, id, email, name, password_hash, role)
VALUES ('00000000-0000-0000-0000-000000000002', '00000000-0000-0000-0000-000000000003',
        'operador@example.test', 'Operador', 'fixture', 'operator');
INSERT INTO nexus_atende.customers (tenant_id, id, chat_id) VALUES
    ('00000000-0000-0000-0000-000000000001', '00000000-0000-0000-0000-000000000004', 'test@c.us'),
    ('00000000-0000-0000-0000-000000000002', '00000000-0000-0000-0000-000000000005', 'test@c.us');

SET LOCAL ROLE nexus_atende_app;
DO $$
BEGIN
    ASSERT (SELECT count(*) FROM nexus_atende.customers) = 0, 'Missing scope exposed customers';
    PERFORM set_config('nexus.tenant_id', '00000000-0000-0000-0000-000000000001', true);
    ASSERT (SELECT count(*) FROM nexus_atende.customers) = 1, 'Customer read escaped tenant';
    ASSERT (SELECT count(*) FROM nexus_atende.users) = 0, 'User read escaped tenant';

    BEGIN
        INSERT INTO nexus_atende.customers (tenant_id, chat_id)
        VALUES ('00000000-0000-0000-0000-000000000002', 'other@c.us');
        RAISE EXCEPTION 'Cross-tenant customer write succeeded';
    EXCEPTION WHEN insufficient_privilege THEN
        NULL;
    END;

    INSERT INTO nexus_atende.conversations (tenant_id, customer_id)
    VALUES ('00000000-0000-0000-0000-000000000001', '00000000-0000-0000-0000-000000000004');

    BEGIN
        UPDATE nexus_atende.conversations
        SET state = 'assigned', assigned_user_id = '00000000-0000-0000-0000-000000000003';
        RAISE EXCEPTION 'Cross-tenant assignment succeeded';
    EXCEPTION WHEN foreign_key_violation THEN
        NULL;
    END;
END $$;

ROLLBACK;
