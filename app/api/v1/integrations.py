"""Per-user third-party credential management.

Secrets are write-only over the API: they can be created and replaced, never
read back. Responses carry a masked fingerprint so the UI can show *which*
token is connected without ever re-exposing it.
"""

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.config import settings
from app.core.database import get_db
from app.core.rate_limit import limiter
from app.models.integration import SUPPORTED_PROVIDERS
from app.schemas.integration import IntegrationCreate, IntegrationResponse
from app.services.audit_service import record_audit_event_best_effort
from app.services.credential_service import (
    CredentialError,
    delete_credential,
    list_integrations,
    store_credential,
)

router = APIRouter(prefix="/integrations", tags=["integrations"])


def _require_encryption_configured() -> None:
    if not settings.credential_encryption_keys:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Credential storage is unavailable because CREDENTIAL_ENCRYPTION_KEYS "
                "is not configured on this deployment"
            ),
        )


@router.get("/providers")
def supported_providers(current_user=Depends(get_current_user)):
    return {"providers": sorted(SUPPORTED_PROVIDERS)}


@router.get("", response_model=list[IntegrationResponse])
def list_connected(db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    return list_integrations(db, user_id=current_user.id)


@router.put("", response_model=IntegrationResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("20/hour")
def connect_provider(
    request: Request,
    payload: IntegrationCreate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    _require_encryption_configured()
    try:
        integration = store_credential(
            db,
            user_id=current_user.id,
            provider=payload.provider,
            secret=payload.secret,
            display_name=payload.display_name,
            scopes=payload.scopes,
        )
    except CredentialError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    record_audit_event_best_effort(
        user_id=current_user.id,
        event="integration.connected",
        resource_type="integration",
        resource_id=payload.provider,
    )
    return integration


@router.delete("/{provider}", status_code=status.HTTP_200_OK)
@limiter.limit(settings.rate_limit_default)
def disconnect_provider(
    request: Request,
    provider: str,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    try:
        removed = delete_credential(db, user_id=current_user.id, provider=provider)
    except CredentialError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    if not removed:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Provider is not connected"
        )

    record_audit_event_best_effort(
        user_id=current_user.id,
        event="integration.disconnected",
        resource_type="integration",
        resource_id=provider.lower(),
    )
    return {"status": "disconnected", "provider": provider.lower()}
