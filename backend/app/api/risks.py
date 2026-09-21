import datetime as dt
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import check_object_access, get_accessible_object_ids, get_current_user, require_role
from app.core.db import get_db
from app.models.entities import AuditLog, Channel, Decision, Prediction, RiskCase, User
from app.models.enums import RiskCaseStatus, UserRole
from app.schemas.schemas import DecisionIn, DecisionOut, RiskCaseOut
from app.services.maintenance_requests import ensure_request_for_dispatch

router = APIRouter(prefix="/risk-cases", tags=["risks"], dependencies=[Depends(get_current_user)])


@router.get(
    "",
    response_model=list[RiskCaseOut],
    summary="Получить список риск-кейсов",
    description=(
        "Фильтры по status и category. Сортировка sort_by: opened_at или probability; sort_dir: asc "
        "или desc. По умолчанию — новые первыми. Учитывает доступ к объектам."
    ),
    responses={
        401: {
            "description": "Требуется вход или токен недействителен",
        },
        200: {
            "description": "Страница записей",
            "headers": {
                "X-Total-Count": {
                    "description": "Всего записей с учётом фильтров, до limit и offset",
                    "schema": {
                        "type": "integer",
                    },
                },
            },
        },
    },
)
def list_risk_cases(
    response: Response,
    status_filter: RiskCaseStatus | None = Query(None, alias="status"),
    category: str | None = None,
    sort_by: Literal["opened_at", "probability"] = "opened_at",
    sort_dir: Literal["asc", "desc"] = "desc",
    limit: int = Query(50, le=500),
    offset: int = 0,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[RiskCaseOut]:
    # Вероятность последнего прогноза по риск-кейсу — не хранится на самом RiskCase (это
    # неизменяемый журнал Prediction, раздел 9.2 плана), поэтому вычисляется здесь как
    # коррелированный подзапрос, а не отдельным N+1 обращением на строку.
    latest_probability = (
        select(Prediction.probability)
        .where(Prediction.risk_case_id == RiskCase.id)
        .order_by(Prediction.created_at.desc())
        .limit(1)
        .correlate(RiskCase)
        .scalar_subquery()
    )

    stmt = select(RiskCase, latest_probability.label("probability"))
    if status_filter:
        stmt = stmt.where(RiskCase.status == status_filter)
    if category:
        stmt = stmt.where(RiskCase.category == category)
    accessible = get_accessible_object_ids(user, db)
    if accessible is not None:
        stmt = stmt.join(Channel, Channel.id == RiskCase.channel_id).where(
            Channel.object_id.in_(accessible)
        )

    # Пагинация по всем страницам (не только "последние N") — раздел «Риски» и остальные
    # списки админки иначе показывали только первую страницу без способа посмотреть
    # остальное (см. docs/Статус.md, запись 21 сентября). Total считаем тем же набором
    # фильтров, но без join/order по вероятности (та нужна только для сортировки, не влияет
    # на количество строк) — отдельный дешёвый count(*) по RiskCase.
    count_stmt = select(func.count()).select_from(RiskCase)
    if status_filter:
        count_stmt = count_stmt.where(RiskCase.status == status_filter)
    if category:
        count_stmt = count_stmt.where(RiskCase.category == category)
    if accessible is not None:
        count_stmt = count_stmt.join(Channel, Channel.id == RiskCase.channel_id).where(
            Channel.object_id.in_(accessible)
        )
    response.headers["X-Total-Count"] = str(db.scalar(count_stmt) or 0)

    order_col = latest_probability if sort_by == "probability" else RiskCase.opened_at
    stmt = stmt.order_by(order_col.desc() if sort_dir == "desc" else order_col.asc())

    rows = db.execute(stmt.offset(offset).limit(limit)).all()
    return [
        RiskCaseOut(
            id=rc.id,
            channel_id=rc.channel_id,
            category=rc.category,
            status=rc.status,
            priority=rc.priority,
            opened_at=rc.opened_at,
            closed_at=rc.closed_at,
            latest_probability=proba,
        )
        for rc, proba in rows
    ]


@router.get(
    "/{risk_case_id}",
    response_model=RiskCaseOut,
    summary="Получить риск-кейс по ID",
    description="Учитывает доступ к объекту.",
    responses={
        403: {
            "description": "Нет доступа к объекту",
        },
        404: {
            "description": "Риск-кейс не найден",
        },
        401: {
            "description": "Требуется вход или токен недействителен",
        },
    },
)
def get_risk_case(
    risk_case_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> RiskCase:
    rc = db.get(RiskCase, risk_case_id)
    if rc is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Риск-кейс не найден")
    check_object_access(rc.channel.object_id, user, db)
    return rc


@router.post(
    "/{risk_case_id}/decisions",
    response_model=DecisionOut,
    summary="Принять решение по риску",
    description=(
        "Доступно диспетчеру, аналитику и администратору с доступом к объекту. observe переводит "
        "риск в observing; dispatch — в dispatched и создаёт или связывает заявку; reject закрывает "
        "риск как rejected; clarify записывает запрос уточнения без смены статуса."
    ),
    responses={
        403: {
            "description": "Недостаточно прав или нет доступа к объекту",
        },
        404: {
            "description": "Риск-кейс не найден",
        },
        401: {
            "description": "Требуется вход или токен недействителен",
        },
    },
)
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
    check_object_access(rc.channel.object_id, user, db)

    old_status = rc.status
    decision = Decision(risk_case_id=risk_case_id, user_id=user.id, action=payload.action, reason=payload.reason)
    db.add(decision)

    if payload.action.value == "reject":
        rc.status = RiskCaseStatus.rejected
        rc.closed_at = dt.datetime.now(dt.timezone.utc)
    elif payload.action.value == "dispatch":
        rc.status = RiskCaseStatus.dispatched
        # Раньше решение диспетчера и заявка на обслуживание были не связаны — «направить на
        # проверку» ничего не создавало в разделе «Заявки», если раньше не сработало
        # авто-правило worker'а по порогу вероятности (см. docs/Статус.md). Идемпотентно.
        ensure_request_for_dispatch(db, rc, rc.channel, user, payload.reason)
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
