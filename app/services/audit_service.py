import json

from sqlalchemy.orm import Session

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
    metadata: dict | None = None,
    commit: bool = True,
) -> None:
    safe_metadata = metadata or {}
    db.add(
        AuditLog(
            user_id=user_id,
            request_id=get_request_id(),
            event=event,
            resource_type=resource_type,
            resource_id=resource_id,
            status=status,
            metadata_json=json.dumps(safe_metadata, ensure_ascii=False, separators=(",", ":")),
        )
    )
    if commit:
        db.commit()
