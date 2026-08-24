from datetime import UTC, datetime

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    HTTPException,
    Query,
    Request,
    UploadFile,
    status,
)
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.config import settings
from app.core.database import get_db
from app.core.plans import get_plan_policy
from app.core.rate_limit import limiter
from app.models.document import Document
from app.schemas.document import (
    DocumentCreate,
    DocumentResponse,
    DocumentSearchRequest,
    DocumentSearchResult,
)
from app.services.document_ingestion import DocumentExtractionError, extract_text
from app.services.embedding_usage_service import embedding_usage_summary
from app.services.rag_jobs import process_document_index
from app.services.rag_quota import (
    DocumentLimitExceededError,
    EmbeddingQuotaExceededError,
    embedding_quota_snapshot,
    enforce_indexing_allowed,
)
from app.services.rag_service import (
    DocumentIndexInProgressError,
    DuplicateDocumentError,
    RAGError,
    create_pending_document,
    delete_document,
    reindex_document,
    retrieve_chunks,
)

router = APIRouter(prefix="/rag", tags=["rag"])

#: Bound on how many documents one list response may return. Without it a
#: heavy account returns an unbounded payload.
MAX_PAGE_SIZE = 100


def _guard_indexing(db: Session, current_user, *, text: str, is_new_document: bool) -> None:
    """Refuse work that would exceed the plan's indexing budget.

    Checked before the provider call, because after it the money is spent.
    """
    try:
        enforce_indexing_allowed(
            db,
            user_id=current_user.id,
            policy=get_plan_policy(getattr(current_user, "role", None)),
            text=text,
            is_new_document=is_new_document,
        )
    except DocumentLimitExceededError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except EmbeddingQuotaExceededError as exc:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=str(exc)) from exc


@router.post("/documents", response_model=DocumentResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit(settings.rate_limit_chat)
def create_document(
    request: Request,
    payload: DocumentCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    _guard_indexing(db, current_user, text=payload.content, is_new_document=True)
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


@router.post(
    "/documents/upload", response_model=DocumentResponse, status_code=status.HTTP_201_CREATED
)
@limiter.limit(settings.rate_limit_chat)
def upload_document(
    request: Request,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    try:
        content = file.file.read(settings.document_max_upload_bytes + 1)
        if len(content) > settings.document_max_upload_bytes:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail="Document exceeds the upload size limit",
            )
        text, mime_type, source = extract_text(file.filename or "document", content)
        _guard_indexing(db, current_user, text=text, is_new_document=True)
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
def list_documents(
    limit: int = Query(default=50, ge=1, le=MAX_PAGE_SIZE),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    return (
        db.query(Document)
        .filter(Document.user_id == current_user.id)
        .order_by(Document.id.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )


@router.get("/usage")
@limiter.limit(settings.rate_limit_default)
def get_embedding_usage(
    request: Request,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    since = datetime.now(UTC).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    summary = embedding_usage_summary(db, user_id=current_user.id, since=since)
    # Consumption without the ceiling is not actionable for the user.
    summary.update(
        embedding_quota_snapshot(
            db,
            user_id=current_user.id,
            policy=get_plan_policy(getattr(current_user, "role", None)),
        )
    )
    return summary


@router.post("/documents/{document_id}/reindex", response_model=DocumentResponse)
@limiter.limit("10/hour")
def reindex_one_document(
    request: Request,
    document_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    existing = (
        db.query(Document)
        .filter(Document.id == document_id, Document.user_id == current_user.id)
        .first()
    )
    if existing is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    _guard_indexing(db, current_user, text=existing.raw_text, is_new_document=False)

    try:
        document = reindex_document(db, user_id=current_user.id, document_id=document_id)
        background_tasks.add_task(process_document_index, document.id)
        return document
    except DocumentIndexInProgressError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except RAGError as exc:
        status_code = (
            status.HTTP_404_NOT_FOUND
            if str(exc) == "Document not found"
            else status.HTTP_400_BAD_REQUEST
        )
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc


@router.delete("/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit(settings.rate_limit_default)
def delete_one_document(
    request: Request,
    document_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    try:
        delete_document(db, user_id=current_user.id, document_id=document_id)
    except RAGError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return None


@router.post("/search", response_model=list[DocumentSearchResult])
@limiter.limit(settings.rate_limit_chat)
def search_documents(
    request: Request,
    payload: DocumentSearchRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    try:
        results = retrieve_chunks(
            db, user_id=current_user.id, query=payload.query, limit=payload.limit
        )
    except RAGError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from exc
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
