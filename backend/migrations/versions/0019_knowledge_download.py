"""Keep the original bytes of imported knowledge files."""

from alembic import op

revision = "0019_knowledge_download"
down_revision = "0018_assistant_name"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE nexus_atende.knowledge_chunks
            ADD COLUMN original_kind text,
            ADD COLUMN original_bytes bytea,
            ADD CHECK (
                (original_kind IS NULL AND original_bytes IS NULL)
                OR (position = 0 AND original_kind IS NOT NULL
                    AND original_kind IN ('txt', 'md', 'pdf', 'docx')
                    AND original_bytes IS NOT NULL AND octet_length(original_bytes) <= 4194304)
            );
    """)


def downgrade() -> None:
    raise RuntimeError("Downgrade would discard original knowledge files.")
