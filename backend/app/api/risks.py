import datetime as dt

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_role
from app.core.db import get_db
from app.models.entities import AuditLog, Decision, RiskCase, User
from app.models.enums import RiskCaseStatus, UserRole
from app.schemas.schemas import DecisionIn, DecisionOut, RiskCaseOut

router = APIRouter(prefix="/risk-cases", tags=["risks"], dependencies=[Depends(get_current_user)])


@router.get("", response_model=list[RiskCaseOut])
def list_risk_cases(
    status_filter: RiskCaseStatus | None = Query(None, alias="status"),
    category: str | None = None,
    limit: int = Query(50, le=500),
    offset: int = 0,
    db: Session = Depends(get_db),
) -> list[RiskCase]:
    stmt = select(RiskCase)
    if status_filter:
        stmt = stmt.where(RiskCase.status == status_filter)
    if category:
        stmt = stmt.where(RiskCase.category == category)
    stmt = stmt.order_by(RiskCase.opened_at.desc())
    return list(db.scalars(stmt.offset(offset).limit(limit)))


@router.get("/{risk_case_id}", response_model=RiskCaseOut)
def get_risk_case(risk_case_id: int, db: Session = Depends(get_db)) -> RiskCase:
    rc = db.get(RiskCase, risk_case_id)
    if rc is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Риск-кейс не найден")
    return rc


@router.post("/{risk_case_id}/decisions", response_model=DecisionOut)
def add_decision(
    risk_case_id: int,
    payload: DecisionIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_role(UserRole.dispatcher, UserRole.analyst, UserRole.admin)),
) -> Decision:
    """Решение диспетчера. Прогноз и решение — разные сущности (раздел 9.1 плана)."""
    rc = db.get(RiskCase, risk_case_id)
    if rc is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Риск-кейс не найден")

    old_status = rc.status
    decision = Decision(risk_case_id=risk_case_id, user_id=user.id, action=payload.action, reason=payload.reason)
    db.add(decision)

    if payload.action.value == "reject":
        rc.status = RiskCaseStatus.rejected
        rc.closed_at = dt.datetime.now(dt.timezone.utc)
    elif payload.action.value == "dispatch":
        rc.status = RiskCaseStatus.dispatched
    elif payload.action.value == "observe":
        rc.status = RiskCaseStatus.observing

    db.add(
        AuditLog(
            user_id=user.id,
            role=user.role.value,
            entity_type="risk_case",
            entity_id=rc.id,
            old_state={"status": old_status.value},
            new_state={"status": rc.status.value},
            reason=payload.reason,
        )
    )
    db.commit()
    db.refresh(decision)
    return decision
