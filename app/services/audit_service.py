import json
from collections.abc import Mapping

from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.core.observability import get_request_id
from app.models.audit_log import AuditLog


def record_audit_event(
    db: Session,
    *,
    user_id: int | None,
    event: str,
    status: str = "success",
    resource_type: str | None = None,
    resource_id: str | None = None,
    metadata: Mapping[str, object] | None = None,
    commit: bool = True,
) -> None:
    db.add(
        AuditLog(
            user_id=user_id,
            request_id=get_request_id(),
            event=event,
            resource_type=resource_type,
            resource_id=resource_id,
            status=status,
            metadata_json=json.dumps(
                dict(metadata or {}), ensure_ascii=False, separators=(",", ":")
            ),
        )
    )
    if commit:
        db.commit()


def record_audit_event_best_effort(
    *,
    user_id: int | None,
    event: str,
    status: str = "success",
    resource_type: str | None = None,
    resource_id: str | None = None,
    metadata: Mapping[str, object] | None = None,
) -> None:
    """Persist security/operations metadata without becoming a request dependency."""
    db = SessionLocal()
    try:
        record_audit_event(
            db,
            user_id=user_id,
            event=event,
            status=status,
            resource_type=resource_type,
            resource_id=resource_id,
            metadata=metadata,
        )
    except Exception:
        db.rollback()
    finally:
        db.close()
