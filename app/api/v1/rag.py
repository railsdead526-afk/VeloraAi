from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.document import Document
from app.schemas.document import DocumentCreate, DocumentResponse, DocumentSearchRequest, DocumentSearchResult
from app.services.rag_service import RAGError, ingest_text, retrieve_chunks

router = APIRouter(prefix="/rag", tags=["rag"])


@router.post("/documents", response_model=DocumentResponse, status_code=status.HTTP_201_CREATED)
def create_document(payload: DocumentCreate, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    try:
        return ingest_text(
            db,
            user_id=current_user.id,
            name=payload.name,
            text=payload.content,
            source=payload.source,
            mime_type=payload.mime_type,
        )
    except RAGError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc


@router.get("/documents", response_model=list[DocumentResponse])
def list_documents(db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    return (
        db.query(Document)
        .filter(Document.user_id == current_user.id)
        .order_by(Document.created_at.desc())
        .all()
    )


@router.post("/search", response_model=list[DocumentSearchResult])
def search_documents(payload: DocumentSearchRequest, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    try:
        results = retrieve_chunks(db, user_id=current_user.id, query=payload.query, limit=payload.limit)
    except RAGError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    return [
        DocumentSearchResult(
            document_id=chunk.document_id,
            document_name=chunk.document.name,
            chunk_index=chunk.chunk_index,
            content=chunk.content,
            distance=distance,
        )
        for chunk, distance in results
    ]
