"""add document lifecycle metadata

Revision ID: 0006_document_lifecycle
Revises: 0005_rag_documents
"""

from alembic import op
import sqlalchemy as sa


revision = "0006_document_lifecycle"
down_revision = "0005_rag_documents"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("documents", sa.Column("content_hash", sa.String(length=64), nullable=True))
    op.add_column("documents", sa.Column("raw_text", sa.Text(), nullable=True))

    documents = sa.table(
        "documents",
        sa.column("id", sa.Integer),
        sa.column("content_hash", sa.String(length=64)),
        sa.column("raw_text", sa.Text),
    )
    op.execute(
        documents.update()
        .where(documents.c.content_hash.is_(None))
        .values(content_hash=sa.literal("legacy-") + sa.cast(documents.c.id, sa.String))
    )
    op.execute(
        documents.update()
        .where(documents.c.raw_text.is_(None))
        .values(raw_text=sa.literal(""))
    )

    with op.batch_alter_table("documents") as batch_op:
        batch_op.alter_column("content_hash", existing_type=sa.String(length=64), nullable=False)
        batch_op.alter_column("raw_text", existing_type=sa.Text(), nullable=False)
        batch_op.create_unique_constraint("uq_documents_user_content_hash", ["user_id", "content_hash"])

    op.create_index("ix_documents_content_hash", "documents", ["content_hash"])


def downgrade():
    op.drop_index("ix_documents_content_hash", table_name="documents")
    with op.batch_alter_table("documents") as batch_op:
        batch_op.drop_constraint("uq_documents_user_content_hash", type_="unique")
        batch_op.drop_column("raw_text")
        batch_op.drop_column("content_hash")
