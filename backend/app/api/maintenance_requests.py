import datetime as dt

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_role
from app.core.db import get_db
from app.models.entities import AuditLog, MaintenanceRequest, User
from app.models.enums import MaintenanceRequestStatus, UserRole
from app.schemas.schemas import MaintenanceRequestOut, TransitionIn

router = APIRouter(
    prefix="/maintenance-requests", tags=["maintenance"], dependencies=[Depends(get_current_user)]
)

# Раздел 10 плана: draft -> approved -> in_progress -> completed; + rejected, cancelled.
ALLOWED_TRANSITIONS: dict[MaintenanceRequestStatus, set[MaintenanceRequestStatus]] = {
    MaintenanceRequestStatus.draft: {MaintenanceRequestStatus.approved, MaintenanceRequestStatus.rejected},
    MaintenanceRequestStatus.approved: {
        MaintenanceRequestStatus.in_progress,
        MaintenanceRequestStatus.cancelled,
    },
    MaintenanceRequestStatus.in_progress: {
        MaintenanceRequestStatus.completed,
        MaintenanceRequestStatus.cancelled,
    },
    MaintenanceRequestStatus.completed: set(),
    MaintenanceRequestStatus.rejected: set(),
    MaintenanceRequestStatus.cancelled: set(),
}


@router.get("", response_model=list[MaintenanceRequestOut])
def list_maintenance_requests(
    status_filter: MaintenanceRequestStatus | None = Query(None, alias="status"),
    limit: int = Query(50, le=500),
    offset: int = 0,
    db: Session = Depends(get_db),
) -> list[MaintenanceRequest]:
    stmt = select(MaintenanceRequest)
    if status_filter:
        stmt = stmt.where(MaintenanceRequest.status == status_filter)
    stmt = stmt.order_by(MaintenanceRequest.created_at.desc())
    return list(db.scalars(stmt.offset(offset).limit(limit)))


def _transition(
    request_id: int,
    to_status: MaintenanceRequestStatus,
    reason: str | None,
    db: Session,
    user: User,
) -> MaintenanceRequest:
    mr = db.get(MaintenanceRequest, request_id)
    if mr is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Заявка не найдена")
    allowed = ALLOWED_TRANSITIONS.get(mr.status, set())
    if to_status not in allowed:
        raise HTTPException(
            status.HTTP_409_CONFLICT, f"Переход {mr.status.value} -> {to_status.value} не разрешён"
        )
    old_status = mr.status
    mr.status = to_status
    if to_status == MaintenanceRequestStatus.approved:
        mr.approved_by_user_id = user.id
        mr.approved_at = dt.datetime.now(dt.timezone.utc)
    db.add(
        AuditLog(
            user_id=user.id,
            role=user.role.value,
            entity_type="maintenance_request",
            entity_id=mr.id,
            old_state={"status": old_status.value},
            new_state={"status": to_status.value},
            reason=reason,
        )
    )
    db.commit()
    db.refresh(mr)
    return mr


@router.post("/{request_id}/approve", response_model=MaintenanceRequestOut)
def approve(
    request_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_role(UserRole.dispatcher, UserRole.admin)),
) -> MaintenanceRequest:
    return _transition(request_id, MaintenanceRequestStatus.approved, None, db, user)


@router.post("/{request_id}/transitions", response_model=MaintenanceRequestOut)
def transition(
    request_id: int,
    payload: TransitionIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_role(UserRole.dispatcher, UserRole.admin)),
) -> MaintenanceRequest:
    return _transition(request_id, payload.to_status, payload.reason, db, user)
