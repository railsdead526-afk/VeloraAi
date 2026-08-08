from sqlalchemy.orm import Session
from app.models.item import Item


def create_item(db: Session, name: str, description: str, owner_id: int) -> Item:
    item = Item(name=name, description=description, owner_id=owner_id)
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


def get_items(
    db: Session,
    owner_id: int,
    skip: int = 0,
    limit: int = 10,
    search: str | None = None,
    sort_by: str = "id",
    order: str = "asc",
):
    query = db.query(Item).filter(Item.owner_id == owner_id)

    if search:
        query = query.filter(Item.name.ilike(f"%{search}%"))

    if sort_by == "name":
        sort_column = Item.name
    else:
        sort_column = Item.id

    if order == "desc":
        query = query.order_by(sort_column.desc())
    else:
        query = query.order_by(sort_column.asc())

    total = query.count()
    items = query.offset(skip).limit(limit).all()

    return {
        "total": total,
        "skip": skip,
        "limit": limit,
        "items": items,
    }


def get_item_by_id(db: Session, item_id: int, owner_id: int) -> Item | None:
    return db.query(Item).filter(Item.id == item_id, Item.owner_id == owner_id).first()


def update_item(db: Session, item_id: int, owner_id: int, name: str, description: str) -> Item | None:
    item = get_item_by_id(db, item_id, owner_id)
    if not item:
        return None

    item.name = name
    item.description = description
    db.commit()
    db.refresh(item)
    return item


def patch_item(
    db: Session,
    item_id: int,
    owner_id: int,
    name: str | None = None,
    description: str | None = None,
) -> Item | None:
    item = get_item_by_id(db, item_id, owner_id)
    if not item:
        return None

    if name is not None:
        item.name = name

    if description is not None:
        item.description = description

    db.commit()
    db.refresh(item)
    return item


def delete_item(db: Session, item_id: int, owner_id: int):
    item = get_item_by_id(db, item_id, owner_id)
    if not item:
        return None

    deleted_item = {
        "id": item.id,
        "name": item.name,
        "description": item.description,
    }

    db.delete(item)
    db.commit()

    return {
        "message": "Item deleted",
        "item": deleted_item,
    }

