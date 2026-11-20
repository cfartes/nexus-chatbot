$ErrorActionPreference = 'Stop'
$container = 'nexus-atende-test-' + [guid]::NewGuid().ToString('N').Substring(0, 8)
$testAdminPassword = [guid]::NewGuid().ToString('N')
$testRuntimePassword = [guid]::NewGuid().ToString('N')
$started = $false

Push-Location (Join-Path $PSScriptRoot '..')
try {
    $migration = uv run --locked alembic upgrade head --sql
    if ($LASTEXITCODE -ne 0) { throw 'Falha ao gerar a migração.' }
    docker run --rm -d --name $container -e POSTGRES_PASSWORD=$testAdminPassword -p 127.0.0.1::5432 pgvector/pgvector:pg17 | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Falha ao iniciar o banco de teste.' }
    $started = $true
    for ($attempt = 0; $attempt -lt 30; $attempt++) {
        docker exec $container pg_isready -h 127.0.0.1 -U postgres | Out-Null
        if ($LASTEXITCODE -eq 0) { break }
        Start-Sleep -Seconds 1
    }
    if ($LASTEXITCODE -ne 0) { throw 'O banco de teste não ficou pronto.' }
    $migration | docker exec -i $container psql -U postgres -v ON_ERROR_STOP=1 | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Falha ao aplicar a migração.' }
    Get-Content -Raw tests/tenant_isolation.sql | docker exec -i $container psql -U postgres -v ON_ERROR_STOP=1 | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Falha no teste SQL de isolamento.' }
    $passwordHash = uv run --locked python -c "from src.services.passwords import hash_password; print(hash_password('test-password-123'))"
    if ($LASTEXITCODE -ne 0) { throw 'Falha ao preparar a senha de teste.' }
@"
CREATE ROLE nexus_atende_runtime LOGIN INHERIT NOSUPERUSER NOBYPASSRLS IN ROLE nexus_atende_app PASSWORD '$testRuntimePassword';
INSERT INTO nexus_atende.tenants (id, name, openwa_session_id, openwa_number_verified, phone_number) VALUES
('00000000-0000-0000-0000-000000000001', 'Nexus', '00000000-0000-0000-0000-000000000003', true, '+5511999999999'),
('00000000-0000-0000-0000-000000000002', 'Outra empresa', NULL, false, NULL);
INSERT INTO nexus_atende.users (tenant_id, email, name, password_hash, role) VALUES
('00000000-0000-0000-0000-000000000001', 'admin@example.test', 'Admin Nexus', '$passwordHash', 'admin'),
('00000000-0000-0000-0000-000000000001', 'first@example.test', 'Primeiro', '$passwordHash', 'operator'),
('00000000-0000-0000-0000-000000000001', 'second@example.test', 'Segundo', '$passwordHash', 'operator');
UPDATE nexus_atende.users SET platform_admin = true WHERE email = 'admin@example.test';
"@ | docker exec -i $container psql -U postgres -v ON_ERROR_STOP=1 | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Falha ao criar os dados de teste.' }

    $runtimePort = (docker port $container 5432/tcp).Split(':')[-1]
    $env:NEXUS_ATENDE_TEST_DATABASE_URL = "postgresql+asyncpg://nexus_atende_runtime:${testRuntimePassword}@127.0.0.1:${runtimePort}/postgres"
    $env:NEXUS_ATENDE_TEST_ADMIN_URL = "postgresql+asyncpg://postgres:${testAdminPassword}@127.0.0.1:${runtimePort}/postgres"
    $env:NEXUS_ATENDE_DATABASE_URL = $env:NEXUS_ATENDE_TEST_DATABASE_URL
    $env:NEXUS_ATENDE_PUBLIC_ORIGIN = 'https://nexus.example.test'
    $env:NEXUS_ATENDE_OPENWA_BASE_URL = 'https://openwa.example.test/api'
    $env:NEXUS_ATENDE_OPENWA_API_KEY = 'test-only'
    $env:NEXUS_ATENDE_OPENAI_API_KEY = ''
    $env:NEXUS_ATENDE_OPENWA_WEBHOOK_SECRET = ''
    $env:NEXUS_ATENDE_OPENWA_WEBHOOK_TENANT_ID = ''

    foreach ($test in @('check_runtime', 'check_auth', 'check_webhook', 'check_conversations', 'check_work')) {
        if ($test -eq 'check_conversations') {
            'DELETE FROM nexus_atende.login_limits;' | docker exec -i $container psql -U postgres -v ON_ERROR_STOP=1 | Out-Null
            if ($LASTEXITCODE -ne 0) { throw 'Falha ao limpar os limites do cenário de login.' }
        }
        uv run --locked python -m "tests.$test"
        if ($LASTEXITCODE -ne 0) { throw "Falha em $test." }
        Write-Output "$test OK"
    }
} finally {
    if ($started) { docker stop $container | Out-Null }
    Pop-Location
}
