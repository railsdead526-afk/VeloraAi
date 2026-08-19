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
    op.execute("UPDATE documents SET content_hash = 'legacy-' || id::text WHERE content_hash IS NULL")
    op.execute("UPDATE documents SET raw_text = '' WHERE raw_text IS NULL")
    op.alter_column("documents", "content_hash", nullable=False)
    op.alter_column("documents", "raw_text", nullable=False)
    op.create_index("ix_documents_content_hash", "documents", ["content_hash"])
    op.create_unique_constraint("uq_documents_user_content_hash", "documents", ["user_id", "content_hash"])


def downgrade():
    op.drop_constraint("uq_documents_user_content_hash", "documents", type_="unique")
    op.drop_index("ix_documents_content_hash", table_name="documents")
    op.drop_column("documents", "raw_text")
    op.drop_column("documents", "content_hash")
