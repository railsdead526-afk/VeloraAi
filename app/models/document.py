import json
from datetime import datetime
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    DateTime,
    Dialect,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import TypeDecorator, TypeEngine

from app.core.database import Base

EMBEDDING_DIMENSIONS = 1536


class EmbeddingType(TypeDecorator[Any]):
    """pgvector in PostgreSQL, JSON text in SQLite.

    Keeping the fallback lets the whole test suite run without a database
    server, while production still gets real vector indexing.
    """

    impl = Vector(EMBEDDING_DIMENSIONS)
    cache_ok = True

    def load_dialect_impl(self, dialect: Dialect) -> TypeEngine[Any]:
        if dialect.name == "sqlite":
            return dialect.type_descriptor(Text())
        return dialect.type_descriptor(Vector(EMBEDDING_DIMENSIONS))

    def process_bind_param(self, value: Any, dialect: Dialect) -> Any:
        if value is None:
            return None
        if dialect.name == "sqlite":
            return json.dumps(value)
        return value

    def process_result_value(self, value: Any, dialect: Dialect) -> Any:
        if value is None:
            return None
        if dialect.name == "sqlite":
            return json.loads(value) if isinstance(value, str) else value
        return value


EMBEDDING_TYPE = EmbeddingType()


class Document(Base):
    __tablename__ = "documents"
    __table_args__ = (
        UniqueConstraint("user_id", "content_hash", name="uq_documents_user_content_hash"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    source: Mapped[str] = mapped_column(String(50), nullable=False, default="text")
    mime_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="ready")
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    raw_text: Mapped[str] = mapped_column(Text, nullable=False)
    indexing_attempts: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    last_index_error: Mapped[str | None] = mapped_column(String(255), nullable=True)
    last_indexed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    user = relationship("User", back_populates="documents")
    chunks = relationship("DocumentChunk", back_populates="document", cascade="all, delete-orphan")


class DocumentChunk(Base):
    __tablename__ = "document_chunks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    document_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    #: A list of floats in PostgreSQL, JSON text in SQLite, so the Python-side
    #: type is dialect dependent.
    embedding: Mapped[Any | None] = mapped_column(EMBEDDING_TYPE, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    document = relationship("Document", back_populates="chunks")
