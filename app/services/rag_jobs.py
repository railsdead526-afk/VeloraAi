from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.models.document import Document, DocumentChunk
from app.services.rag_service import RAGError, embed_texts, chunk_text, normalize_text, content_hash


def process_document_index(document_id: int) -> None:
    db: Session = SessionLocal()
    try:
        document = db.query(Document).filter(Document.id == document_id).first()
        if document is None:
            return
        if document.status not in {"queued", "processing"}:
            return

        document.status = "processing"
        db.commit()

        normalized = normalize_text(document.raw_text)
        chunks = chunk_text(normalized)
        if not chunks:
            raise RAGError("Document text is empty")
        embeddings = embed_texts(chunks)

        db.query(DocumentChunk).filter(DocumentChunk.document_id == document.id).delete(synchronize_session=False)
        for index, (chunk_content, embedding) in enumerate(zip(chunks, embeddings)):
            db.add(
                DocumentChunk(
                    document_id=document.id,
                    chunk_index=index,
                    content=chunk_content,
                    embedding=embedding,
                )
            )
        document.content_hash = content_hash(normalized)
        document.status = "ready"
        db.commit()
    except Exception:
        db.rollback()
        document = db.query(Document).filter(Document.id == document_id).first()
        if document is not None:
            document.status = "failed"
            db.commit()
    finally:
        db.close()
