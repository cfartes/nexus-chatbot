from alembic import context

if not context.is_offline_mode():
    raise RuntimeError("Generate PostgreSQL SQL with alembic upgrade head --sql.")

context.configure(dialect_name="postgresql", transactional_ddl=True)

with context.begin_transaction():
    context.run_migrations()
