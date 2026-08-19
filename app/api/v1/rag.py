from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.config import settings
from app.core.database import get_db
from app.models.document import Document
from app.schemas.document import DocumentCreate, DocumentResponse, DocumentSearchRequest, DocumentSearchResult
from app.services.document_ingestion import DocumentExtractionError, extract_text
from app.services.embedding_usage_service import embedding_usage_summary
from app.services.rag_jobs import process_document_index
from app.services.rag_service import DuplicateDocumentError, RAGError, create_pending_document, delete_document, reindex_document, retrieve_chunks

router = APIRouter(prefix="/rag", tags=["rag"])


@router.post("/documents", response_model=DocumentResponse, status_code=status.HTTP_201_CREATED)
def create_document(
    payload: DocumentCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    try:
        document = create_pending_document(
            db,
            user_id=current_user.id,
            name=payload.name,
            text=payload.content,
            source=payload.source,
            mime_type=payload.mime_type,
        )
        background_tasks.add_task(process_document_index, document.id)
        return document
    except DuplicateDocumentError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except RAGError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("/documents/upload", response_model=DocumentResponse, status_code=status.HTTP_201_CREATED)
def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    try:
        content = file.file.read(settings.document_max_upload_bytes + 1)
        if len(content) > settings.document_max_upload_bytes:
            raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="Document exceeds the upload size limit")
        text, mime_type, source = extract_text(file.filename or "document", content)
        document = create_pending_document(
            db,
            user_id=current_user.id,
            name=file.filename or "document",
            text=text,
            source=source,
            mime_type=mime_type,
        )
        background_tasks.add_task(process_document_index, document.id)
        return document
    except HTTPException:
        raise
    except DuplicateDocumentError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except DocumentExtractionError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except RAGError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get("/documents", response_model=list[DocumentResponse])
def list_documents(db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    return (
        db.query(Document)
        .filter(Document.user_id == current_user.id)
        .order_by(Document.created_at.desc())
        .all()
    )


@router.get("/usage")
def get_embedding_usage(db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    since = datetime.now(timezone.utc).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    return embedding_usage_summary(db, user_id=current_user.id, since=since)


@router.post("/documents/{document_id}/reindex", response_model=DocumentResponse)
def reindex_one_document(
    document_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    try:
        document = reindex_document(db, user_id=current_user.id, document_id=document_id)
        background_tasks.add_task(process_document_index, document.id)
        return document
    except RAGError as exc:
        status_code = status.HTTP_404_NOT_FOUND if str(exc) == "Document not found" else status.HTTP_400_BAD_REQUEST
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc


@router.delete("/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_one_document(document_id: int, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    try:
        delete_document(db, user_id=current_user.id, document_id=document_id)
    except RAGError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return None


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
