from datetime import datetime

from pydantic import BaseModel, Field


class DocumentCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    content: str = Field(min_length=1)
    source: str = Field(default="text", max_length=50)
    mime_type: str | None = Field(default="text/plain", max_length=100)


class DocumentResponse(BaseModel):
    id: int
    name: str
    source: str
    mime_type: str | None
    status: str
    indexing_attempts: int
    last_index_error: str | None
    last_indexed_at: datetime | None
    created_at: datetime
    updated_at: datetime

    class Config:
        orm_mode = True
        from_attributes = True


class DocumentSearchRequest(BaseModel):
    query: str = Field(min_length=1)
    limit: int = Field(default=5, ge=1, le=20)


class DocumentSearchResult(BaseModel):
    document_id: int
    document_name: str
    chunk_index: int
    content: str
    distance: float
