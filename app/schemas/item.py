from pydantic import BaseModel, Field


class ItemCreate(BaseModel):
    name: str = Field(..., min_length=2)
    description: str = Field(..., min_length=3)


class ItemUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2)
    description: str | None = Field(default=None, min_length=3)


class ItemResponse(BaseModel):
    id: int
    name: str
    description: str

    class Config:
        orm_mode = True


class ItemDeleteResponse(BaseModel):
    message: str
    item: ItemResponse


class ItemListResponse(BaseModel):
    total: int
    skip: int
    limit: int
    items: list[ItemResponse]

