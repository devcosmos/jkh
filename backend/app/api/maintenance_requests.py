import datetime as dt

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.api.deps import check_object_access, get_accessible_object_ids, get_current_user, require_role
from app.core.db import get_db
from app.models.entities import AuditLog, Channel, MaintenanceRequest, RiskCase, User
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


def _build_out(mr: MaintenanceRequest, approver_username: str | None) -> MaintenanceRequestOut:
    rc = mr.risk_case
    channel = rc.channel if rc is not None else None
    obj = channel.object if channel is not None else None
    return MaintenanceRequestOut(
        id=mr.id,
        risk_case_id=mr.risk_case_id,
        work_type=mr.work_type,
        justification=mr.justification,
        priority=mr.priority,
        recommended_by=mr.recommended_by,
        status=mr.status,
        approved_by_user_id=mr.approved_by_user_id,
        approved_by_username=approver_username,
        approved_at=mr.approved_at,
        created_at=mr.created_at,
        category=rc.category if rc is not None else None,
        channel_label=(channel.display_name or str(channel.external_channel_id)) if channel is not None else None,
        object_name=obj.name if obj is not None else None,
    )


@router.get("", response_model=list[MaintenanceRequestOut])
def list_maintenance_requests(
    status_filter: MaintenanceRequestStatus | None = Query(None, alias="status"),
    risk_case_id: int | None = None,
    limit: int = Query(50, le=500),
    offset: int = 0,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[MaintenanceRequestOut]:
    """Раздел «Заявки» — обогащён контекстом риск-кейса (канал/объект/направление), чтобы
    по одной строке было понятно, о чём заявка, без перехода в раздел «Риски». `risk_case_id`
    — сквозная ссылка из карточки риска («Смотреть заявку»/бейдж существующей заявки)."""
    stmt = select(MaintenanceRequest).options(
        joinedload(MaintenanceRequest.risk_case).joinedload(RiskCase.channel).joinedload(Channel.object)
    )
    if status_filter:
        stmt = stmt.where(MaintenanceRequest.status == status_filter)
    if risk_case_id is not None:
        stmt = stmt.where(MaintenanceRequest.risk_case_id == risk_case_id)
    accessible = get_accessible_object_ids(user, db)
    if accessible is not None:
        stmt = (
            stmt.join(RiskCase, RiskCase.id == MaintenanceRequest.risk_case_id)
            .join(Channel, Channel.id == RiskCase.channel_id)
            .where(Channel.object_id.in_(accessible))
        )
    stmt = stmt.order_by(MaintenanceRequest.created_at.desc())
    rows = list(db.scalars(stmt.offset(offset).limit(limit)))

    approver_ids = {r.approved_by_user_id for r in rows if r.approved_by_user_id}
    approvers = (
        dict(db.execute(select(User.id, User.username).where(User.id.in_(approver_ids))).all())
        if approver_ids
        else {}
    )
    return [_build_out(r, approvers.get(r.approved_by_user_id)) for r in rows]


def _transition(
    request_id: int,
    to_status: MaintenanceRequestStatus,
    reason: str | None,
    db: Session,
    user: User,
) -> MaintenanceRequestOut:
    mr = db.get(MaintenanceRequest, request_id)
    if mr is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Заявка не найдена")
    check_object_access(mr.risk_case.channel.object_id, user, db)
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
    approver = db.get(User, mr.approved_by_user_id) if mr.approved_by_user_id else None
    return _build_out(mr, approver.username if approver else None)


@router.post("/{request_id}/approve", response_model=MaintenanceRequestOut)
def approve(
    request_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_role(UserRole.dispatcher, UserRole.admin)),
) -> MaintenanceRequestOut:
    return _transition(request_id, MaintenanceRequestStatus.approved, None, db, user)


@router.post("/{request_id}/transitions", response_model=MaintenanceRequestOut)
def transition(
    request_id: int,
    payload: TransitionIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_role(UserRole.dispatcher, UserRole.admin)),
) -> MaintenanceRequestOut:
    return _transition(request_id, payload.to_status, payload.reason, db, user)
