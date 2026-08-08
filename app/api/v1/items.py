from fastapi import APIRouter, HTTPException, Depends, status, Query
from typing import Literal
from sqlalchemy.orm import Session

from app.schemas.item import (
    ItemCreate,
    ItemUpdate,
    ItemResponse,
    ItemDeleteResponse,
    ItemListResponse,
)
from app.core.database import get_db
from app.crud.item import (
    create_item,
    get_items,
    get_item_by_id,
    update_item,
    patch_item,
    delete_item,
)
from app.api.deps import get_current_user
from app.models.user import User

router = APIRouter(tags=["Items"])


@router.post("/items", response_model=ItemResponse, status_code=status.HTTP_201_CREATED)
def create_item_route(
    payload: ItemCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return create_item(db, payload.name, payload.description, current_user.id)


@router.get("/items", response_model=ItemListResponse)
def list_items(
    skip: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=100),
    search: str | None = None,
    sort_by: Literal["id", "name"] = "id",
    order: Literal["asc", "desc"] = "asc",
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return get_items(db, current_user.id, skip, limit, search, sort_by, order)


@router.get("/items/{item_id}", response_model=ItemResponse)
def get_item(
    item_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    item = get_item_by_id(db, item_id, current_user.id)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    return item


@router.put("/items/{item_id}", response_model=ItemResponse)
def update_item_route(
    item_id: int,
    payload: ItemCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    item = update_item(db, item_id, current_user.id, payload.name, payload.description)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    return item


@router.patch("/items/{item_id}", response_model=ItemResponse)
def patch_item_route(
    item_id: int,
    payload: ItemUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    item = patch_item(db, item_id, current_user.id, payload.name, payload.description)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    return item


@router.delete("/items/{item_id}", response_model=ItemDeleteResponse)
def delete_item_route(
    item_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = delete_item(db, item_id, current_user.id)
    if not result:
        raise HTTPException(status_code=404, detail="Item not found")
    return result

